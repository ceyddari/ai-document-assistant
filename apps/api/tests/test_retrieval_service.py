import unicodedata
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EMBEDDING_DIMENSIONS, DocumentChunk, Organization
from app.services import (
    OrganizationNotFoundError,
    RetrievedChunk,
    search_relevant_chunks,
)
from app.services.retrieval_service import fuse_scores


def build_chunk(*, page_number: int = 2, content: str = "İçerik") -> MagicMock:
    chunk = MagicMock(spec=DocumentChunk)
    chunk.id = uuid4()
    chunk.document_id = uuid4()
    chunk.page_number = page_number
    chunk.content = content
    return chunk


def rows_result(rows: list[tuple]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def build_session(*results: MagicMock) -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = MagicMock(spec=Organization)
    session.execute.side_effect = list(results)
    return session


@pytest.mark.asyncio
async def test_search_relevant_chunks_returns_results() -> None:
    organization_id = uuid4()
    query = "Yıllık izin nasıl alınır?"
    query_embedding = [0.1] * EMBEDDING_DIMENSIONS

    embedding_service = MagicMock()
    embedding_service.embed_query = AsyncMock(return_value=query_embedding)

    chunk = build_chunk(content="Yıllık izin talebi sistemden oluşturulur.")
    # The same chunk found by both retrievers is returned once.
    session = build_session(
        rows_result([(chunk, "izin-proseduru.pdf", 0.25)]),
        rows_result([(chunk, "izin-proseduru.pdf", 0.25, 0.4)]),
    )

    chunks = await search_relevant_chunks(
        organization_id=organization_id,
        query=query,
        session=session,
        embedding_service=embedding_service,
        limit=5,
        minimum_similarity=0.35,
    )

    embedding_service.embed_query.assert_awaited_once_with(query)
    assert session.execute.await_count == 2

    assert chunks == [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename="izin-proseduru.pdf",
            page_number=2,
            content="Yıllık izin talebi sistemden oluşturulur.",
            similarity=0.75,
        )
    ]


@pytest.mark.asyncio
async def test_search_relevant_chunks_returns_empty_list_when_no_match() -> None:
    embedding_service = MagicMock()
    embedding_service.embed_query = AsyncMock(
        return_value=[0.1] * EMBEDDING_DIMENSIONS,
    )
    session = build_session(rows_result([]), rows_result([]))

    chunks = await search_relevant_chunks(
        organization_id=uuid4(),
        query="Fesih şartı nedir?",
        session=session,
        embedding_service=embedding_service,
    )

    assert chunks == []
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_search_relevant_chunks_uses_turkish_or_keyword_query_and_nfc() -> None:
    embedding_service = MagicMock()
    embedding_service.embed_query = AsyncMock(return_value=[0.1] * EMBEDDING_DIMENSIONS)
    session = build_session(rows_result([]), rows_result([]))
    nfd_query = unicodedata.normalize("NFD", "GÜNCEL bilgiler")

    await search_relevant_chunks(
        organization_id=uuid4(),
        query=nfd_query,
        session=session,
        embedding_service=embedding_service,
        folder_ids=[uuid4()],
        document_ids=[uuid4()],
    )

    embedding_service.embed_query.assert_awaited_once_with("GÜNCEL bilgiler")
    keyword_sql = str(
        session.execute.await_args_list[1].args[0].compile(dialect=postgresql.dialect())
    )
    assert "plainto_tsquery('turkish'" in keyword_sql
    assert "content_tsv @@" in keyword_sql
    assert "documents.folder_id IN" in keyword_sql
    assert "documents.id IN" in keyword_sql


def test_fuse_scores_adds_keyword_only_matches_with_clamped_similarity() -> None:
    vector_chunk = build_chunk()
    keyword_chunk = build_chunk()

    results = fuse_scores(
        [(vector_chunk, "a.pdf", 0.4)],
        # Cosine distance can exceed 1; similarity must stay inside the DB's [0, 1] check.
        [(keyword_chunk, "b.pdf", 1.3, 0.9)],
        limit=5,
    )

    assert [result.chunk_id for result in results] == [vector_chunk.id, keyword_chunk.id]
    assert results[1].similarity == 0.0


def test_fuse_scores_keyword_bonus_breaks_near_ties_but_not_large_gaps() -> None:
    close_vector = build_chunk()
    close_keyword = build_chunk()
    far_keyword = build_chunk()

    results = fuse_scores(
        [
            (close_vector, "a.pdf", 0.300),
            (close_keyword, "a.pdf", 0.301),
            (far_keyword, "a.pdf", 0.700),
        ],
        [(close_keyword, "a.pdf", 0.301, 0.5), (far_keyword, "a.pdf", 0.700, 0.9)],
        limit=2,
    )

    assert [result.chunk_id for result in results] == [close_keyword.id, close_vector.id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "limit", "error_message"),
    [
        ("   ", 5, "Soru boş olamaz"),
        ("Yıllık izin?", 0, "Sonuç limiti"),
        ("Yıllık izin?", 21, "Sonuç limiti"),
    ],
)
async def test_search_relevant_chunks_rejects_invalid_input(
    query: str,
    limit: int,
    error_message: str,
) -> None:
    embedding_service = MagicMock()
    embedding_service.embed_query = AsyncMock()
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(ValueError, match=error_message):
        await search_relevant_chunks(
            organization_id=uuid4(),
            query=query,
            session=session,
            embedding_service=embedding_service,
            limit=limit,
        )

    embedding_service.embed_query.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_relevant_chunks_rejects_unknown_organization() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = None
    embedding_service = MagicMock()
    embedding_service.embed_query = AsyncMock()

    with pytest.raises(OrganizationNotFoundError, match="Organizasyon bulunamadı"):
        await search_relevant_chunks(
            organization_id=uuid4(),
            query="Yıllık izin nasıl alınır?",
            session=session,
            embedding_service=embedding_service,
        )

    embedding_service.embed_query.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_relevant_chunks_rejects_invalid_similarity() -> None:
    session = AsyncMock(spec=AsyncSession)
    embedding_service = MagicMock()
    embedding_service.embed_query = AsyncMock()

    with pytest.raises(ValueError, match="Minimum benzerlik"):
        await search_relevant_chunks(
            organization_id=uuid4(),
            query="Yıllık izin nasıl alınır?",
            session=session,
            embedding_service=embedding_service,
            minimum_similarity=1.1,
        )

    session.get.assert_not_awaited()
    embedding_service.embed_query.assert_not_awaited()
