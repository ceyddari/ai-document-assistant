from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EMBEDDING_DIMENSIONS, DocumentChunk, Organization
from app.services import (
    OrganizationNotFoundError,
    RetrievedChunk,
    search_relevant_chunks,
)


@pytest.mark.asyncio
async def test_search_relevant_chunks_returns_results() -> None:
    organization_id = uuid4()
    document_id = uuid4()
    chunk_id = uuid4()
    query = "Yıllık izin nasıl alınır?"
    query_embedding = [0.1] * EMBEDDING_DIMENSIONS

    embedding_service = MagicMock()
    embedding_service.embed_query = AsyncMock(return_value=query_embedding)

    chunk = MagicMock(spec=DocumentChunk)
    chunk.id = chunk_id
    chunk.document_id = document_id
    chunk.page_number = 2
    chunk.content = "Yıllık izin talebi sistemden oluşturulur."

    result = MagicMock()
    result.all.return_value = [
        (chunk, "izin-proseduru.pdf", 0.25),
    ]

    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = MagicMock(spec=Organization)
    session.execute.return_value = result

    chunks = await search_relevant_chunks(
        organization_id=organization_id,
        query=query,
        session=session,
        embedding_service=embedding_service,
        limit=5,
        minimum_similarity=0.35,
    )

    embedding_service.embed_query.assert_awaited_once_with(query)
    session.execute.assert_awaited_once()

    assert chunks == [
        RetrievedChunk(
            chunk_id=chunk_id,
            document_id=document_id,
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

    result = MagicMock()
    result.all.return_value = []

    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = MagicMock(spec=Organization)
    session.execute.return_value = result

    chunks = await search_relevant_chunks(
        organization_id=uuid4(),
        query="Fesih şartı nedir?",
        session=session,
        embedding_service=embedding_service,
    )

    assert chunks == []
    session.execute.assert_awaited_once()


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
