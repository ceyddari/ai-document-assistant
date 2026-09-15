from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocumentStatus
from app.services.embedding_service import EmbeddingService


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int
    content: str
    similarity: float


async def search_relevant_chunks(
    *,
    organization_id: UUID,
    query: str,
    session: AsyncSession,
    embedding_service: EmbeddingService,
    limit: int = 5,
) -> list[RetrievedChunk]:
    if not query.strip():
        raise ValueError("Soru boş olamaz.")

    if not 1 <= limit <= 20:
        raise ValueError("Sonuç limiti 1 ile 20 arasında olmalıdır.")

    query_embedding = await embedding_service.embed_query(query)

    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding,
    ).label("distance")

    statement = (
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
        .order_by(distance)
        .limit(limit)
    )

    result = await session.execute(statement)

    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            page_number=chunk.page_number,
            content=chunk.content,
            similarity=1.0 - float(chunk_distance),
        )
        for chunk, filename, chunk_distance in result.all()
    ]
