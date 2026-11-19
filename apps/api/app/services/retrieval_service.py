import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Row, Text, and_, cast, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TEXT_SEARCH_CONFIG, Document, DocumentChunk, DocumentStatus, Organization
from app.services.document_service import OrganizationNotFoundError
from app.services.embedding_service import EmbeddingService

# Keyword matches add a bonus on top of vector similarity instead of competing by rank.
# Rank fusion (RRF) was measured worse: it erases vector confidence, and ts_rank has no IDF,
# so common words outvote rare exact terms. 0.05 was the only value with hit@5 = 100% on
# storage/eval (0-0.15 within one case of each other; 0.2+ hurts). It mainly rescues exact
# titles/codes that vectors miss. Re-run scripts/evaluate_retrieval.py before changing it.
KEYWORD_SCORE_WEIGHT = 0.05
MIN_CANDIDATES_PER_RETRIEVER = 20
CANDIDATES_PER_RESULT = 4
SUMMARY_CHUNK_LIMIT = 48
# A printed table of contents sits in the front matter and rarely spans more than three pages.
CONTENTS_PAGE_LIMIT = 20
CONTENTS_SPAN_PAGES = 2
CONTENTS_CHUNK_LIMIT = 12


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int
    content: str
    similarity: float


def fuse_scores(
    vector_rows: Sequence[Row],
    keyword_rows: Sequence[Row],
    *,
    limit: int,
) -> list[RetrievedChunk]:
    """Rank the union by similarity + KEYWORD_SCORE_WEIGHT * keyword score.

    vector_rows are (chunk, filename, distance); keyword_rows add a keyword score in [0, 1).
    Ties fall back to chunk id so the order is deterministic.
    """
    rows_by_id: dict[UUID, Row] = {row[0].id: row for row in vector_rows}
    keyword_scores: dict[UUID, float] = {}

    for row in keyword_rows:
        rows_by_id.setdefault(row[0].id, row)
        keyword_scores[row[0].id] = float(row[3])

    def score(chunk_id: UUID) -> float:
        similarity = 1.0 - float(rows_by_id[chunk_id][2])
        return similarity + KEYWORD_SCORE_WEIGHT * keyword_scores.get(chunk_id, 0.0)

    ordered_ids = sorted(rows_by_id, key=lambda chunk_id: (-score(chunk_id), str(chunk_id)))

    return [
        RetrievedChunk(
            chunk_id=row[0].id,
            document_id=row[0].document_id,
            filename=row[1],
            page_number=row[0].page_number,
            content=row[0].content,
            similarity=min(max(1.0 - float(row[2]), 0.0), 1.0),
        )
        for row in (rows_by_id[chunk_id] for chunk_id in ordered_ids[:limit])
    ]


async def search_relevant_chunks(
    *,
    organization_id: UUID,
    query: str,
    session: AsyncSession,
    embedding_service: EmbeddingService,
    limit: int = 5,
    minimum_similarity: float = 0.35,
    folder_ids: list[UUID] | None = None,
    document_ids: list[UUID] | None = None,
) -> list[RetrievedChunk]:
    """Hybrid search: vector similarity boosted by Turkish full-text matches.

    Keyword matches skip the similarity threshold on purpose: exact terms such as codes,
    names or titles are what vectors miss.
    """
    # NFD input (e.g. typed on macOS) would never match NFC document text in full-text search.
    query = unicodedata.normalize("NFC", query)

    if not query.strip():
        raise ValueError("Soru boş olamaz.")

    if not 1 <= limit <= 20:
        raise ValueError("Sonuç limiti 1 ile 20 arasında olmalıdır.")

    if not 0 <= minimum_similarity <= 1:
        raise ValueError("Minimum benzerlik 0 ile 1 arasında olmalıdır.")

    organization = await session.get(Organization, organization_id)

    if organization is None:
        raise OrganizationNotFoundError("Organizasyon bulunamadı.")

    query_embedding = await embedding_service.embed_query(query)

    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding,
    ).label("distance")
    candidate_limit = max(MIN_CANDIDATES_PER_RETRIEVER, limit * CANDIDATES_PER_RESULT)

    base_statement = (
        select(
            DocumentChunk,
            Document.original_filename,
            distance,
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .where(
            DocumentChunk.organization_id == organization_id,
            Document.status == DocumentStatus.READY,
        )
    )

    if folder_ids:
        base_statement = base_statement.where(Document.folder_id.in_(folder_ids))

    # Combined with folders as AND: a selected document outside a mentioned folder is excluded.
    if document_ids:
        base_statement = base_statement.where(Document.id.in_(document_ids))

    vector_statement = (
        base_statement.where(distance <= 1.0 - minimum_similarity)
        .order_by(distance)
        .limit(candidate_limit)
    )

    # Questions are natural language, so match ANY term (OR) and let ranking reward chunks
    # that match more of them; plainto_tsquery's AND would almost never match a full question.
    # The config is inlined: a bound parameter would not resolve to regconfig.
    text_search_config = literal_column(f"'{TEXT_SEARCH_CONFIG}'")
    keyword_query = cast(
        func.replace(
            cast(func.plainto_tsquery(text_search_config, query), Text),
            " & ",
            " | ",
        ),
        TSQUERY,
    )
    # Normalization 32 maps the rank into [0, 1): rank / (rank + 1).
    keyword_rank = func.ts_rank_cd(DocumentChunk.content_tsv, keyword_query, 32).label(
        "keyword_score"
    )
    keyword_statement = (
        base_statement.add_columns(keyword_rank)
        .where(DocumentChunk.content_tsv.op("@@")(keyword_query))
        .order_by(keyword_rank.desc(), distance)
        .limit(candidate_limit)
    )

    vector_rows = (await session.execute(vector_statement)).all()
    keyword_rows = (await session.execute(keyword_statement)).all()

    return fuse_scores(vector_rows, keyword_rows, limit=limit)


async def read_summary_chunks(
    *,
    organization_id: UUID,
    session: AsyncSession,
    folder_ids: list[UUID],
    document_ids: list[UUID] | None,
) -> tuple[list[RetrievedChunk], bool]:
    if not folder_ids and not document_ids:
        raise ValueError("Özet için doküman veya klasör seçilmelidir.")

    in_scope = (
        select(
            DocumentChunk.id,
            func.row_number()
            .over(order_by=(DocumentChunk.document_id, DocumentChunk.chunk_index))
            .label("position"),
            func.count().over().label("total"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.organization_id == organization_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.READY,
        )
    )
    if folder_ids:
        in_scope = in_scope.where(Document.folder_id.in_(folder_ids))
    if document_ids:
        in_scope = in_scope.where(Document.id.in_(document_ids))

    positions = in_scope.subquery()
    # Select the first chunk from each equally sized span over the scope. Small scopes keep every chunk.
    span = func.floor((positions.c.position - 1) * SUMMARY_CHUNK_LIMIT / positions.c.total)
    selected = (
        select(positions.c.id, positions.c.total)
        .distinct(span)
        .order_by(span, positions.c.position)
        .subquery()
    )
    statement = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.original_filename,
            DocumentChunk.page_number,
            DocumentChunk.content,
            selected.c.total,
        )
        .join(selected, selected.c.id == DocumentChunk.id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
    )
    rows = (await session.execute(statement)).all()
    return [RetrievedChunk(*row[:5], similarity=0.0) for row in rows], bool(
        rows and rows[0].total > len(rows)
    )


async def read_document_files(
    *,
    organization_id: UUID,
    session: AsyncSession,
    folder_ids: list[UUID],
    document_ids: list[UUID] | None,
) -> list[tuple[str, str]]:
    """(filename, storage path) of the ready documents in scope, ordered by filename."""
    statement = select(Document.original_filename, Document.storage_path).where(
        Document.organization_id == organization_id,
        Document.status == DocumentStatus.READY,
    )
    if folder_ids:
        statement = statement.where(Document.folder_id.in_(folder_ids))
    if document_ids:
        statement = statement.where(Document.id.in_(document_ids))
    rows = await session.execute(statement.order_by(Document.original_filename))
    return [(row.original_filename, row.storage_path) for row in rows]


async def read_contents_chunks(
    *,
    organization_id: UUID,
    session: AsyncSession,
    folder_ids: list[UUID],
    document_ids: list[UUID] | None,
) -> list[RetrievedChunk]:
    """Chunks of each document's printed table of contents page and the pages right after it."""
    # LIKE per spelling: lower() of the Turkish dotted İ depends on the database locale.
    marker = or_(
        *(DocumentChunk.content.like(f"%{word}%") for word in ("İÇİNDEKİLER", "İçindekiler")),
        DocumentChunk.content.ilike("%table of contents%"),
        DocumentChunk.content.like("%CONTENTS%"),
    )
    scope = [
        DocumentChunk.organization_id == organization_id,
        Document.organization_id == organization_id,
        Document.status == DocumentStatus.READY,
    ]
    if folder_ids:
        scope.append(Document.folder_id.in_(folder_ids))
    if document_ids:
        scope.append(Document.id.in_(document_ids))

    contents_pages = (
        select(DocumentChunk.document_id, func.min(DocumentChunk.page_number).label("page"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(*scope, marker, DocumentChunk.page_number <= CONTENTS_PAGE_LIMIT)
        .group_by(DocumentChunk.document_id)
        .subquery()
    )
    statement = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.original_filename,
            DocumentChunk.page_number,
            DocumentChunk.content,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(
            contents_pages,
            and_(
                contents_pages.c.document_id == DocumentChunk.document_id,
                DocumentChunk.page_number.between(
                    contents_pages.c.page, contents_pages.c.page + CONTENTS_SPAN_PAGES
                ),
            ),
        )
        .where(*scope)
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        .limit(CONTENTS_CHUNK_LIMIT)
    )
    rows = (await session.execute(statement)).all()
    return [RetrievedChunk(*row, similarity=0.0) for row in rows]
