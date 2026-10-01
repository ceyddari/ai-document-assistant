from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.services import (
    EmbeddingServiceError,
    OrganizationNotFoundError,
    RetrievedChunk,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        postgres_db="test_database",
        postgres_user="test_user",
        postgres_password="test_password",
        postgres_host="localhost",
        postgres_port=5432,
        ollama_base_url="http://localhost:11434",
        ollama_embedding_model="bge-m3",
        storage_directory=tmp_path,
    )


@pytest.fixture
def db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def embedding_service(
    monkeypatch: pytest.MonkeyPatch,
) -> MagicMock:
    service = MagicMock()

    monkeypatch.setattr(
        "app.api.routes.search.EmbeddingService",
        MagicMock(return_value=service),
    )

    return service


@pytest.fixture
def search_relevant_chunks_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncMock:
    mock = AsyncMock()

    monkeypatch.setattr(
        "app.api.routes.search.search_relevant_chunks",
        mock,
    )

    return mock


@pytest.fixture
def client(
    db_session: AsyncMock,
    settings: Settings,
) -> Iterator[TestClient]:
    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_semantic_search_returns_retrieved_chunks(
    client: TestClient,
    db_session: AsyncMock,
    embedding_service: MagicMock,
    search_relevant_chunks_mock: AsyncMock,
) -> None:
    organization_id = uuid4()
    document_id = uuid4()
    chunk_id = uuid4()

    search_relevant_chunks_mock.return_value = [
        RetrievedChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            filename="Surpriz_Kasa_Proje_Mimarisi.pdf",
            page_number=1,
            content="Proje mimarisi ve operasyonel akış.",
            similarity=0.6679,
        )
    ]

    response = client.post(
        f"/organizations/{organization_id}/search",
        json={
            "query": "  Sürpriz Kasa projesinin mimarisi nedir?  ",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "query": "Sürpriz Kasa projesinin mimarisi nedir?",
        "items": [
            {
                "chunk_id": str(chunk_id),
                "document_id": str(document_id),
                "filename": "Surpriz_Kasa_Proje_Mimarisi.pdf",
                "page_number": 1,
                "content": "Proje mimarisi ve operasyonel akış.",
                "similarity": 0.6679,
            }
        ],
    }

    search_relevant_chunks_mock.assert_awaited_once_with(
        organization_id=organization_id,
        query="Sürpriz Kasa projesinin mimarisi nedir?",
        session=db_session,
        embedding_service=embedding_service,
        limit=5,
        minimum_similarity=0.35,
    )


@pytest.mark.parametrize(
    "request_body",
    [
        {"query": "   ", "limit": 5},
        {"query": "Geçerli soru", "limit": 0},
        {"query": "Geçerli soru", "limit": 21},
    ],
)
def test_semantic_search_rejects_invalid_request(
    client: TestClient,
    embedding_service: MagicMock,
    search_relevant_chunks_mock: AsyncMock,
    request_body: dict[str, object],
) -> None:
    response = client.post(
        f"/organizations/{uuid4()}/search",
        json=request_body,
    )

    assert response.status_code == 422
    search_relevant_chunks_mock.assert_not_awaited()


@pytest.mark.parametrize(
    ("service_error", "expected_status", "expected_detail"),
    [
        (
            OrganizationNotFoundError("Organizasyon bulunamadı."),
            404,
            "Organizasyon bulunamadı.",
        ),
        (
            EmbeddingServiceError("Ollama unavailable"),
            503,
            "Embedding servisine şu anda erişilemiyor.",
        ),
        (
            SQLAlchemyError("Database unavailable"),
            503,
            "Semantik arama şu anda gerçekleştirilemiyor.",
        ),
    ],
)
def test_semantic_search_maps_service_errors(
    client: TestClient,
    embedding_service: MagicMock,
    search_relevant_chunks_mock: AsyncMock,
    service_error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    search_relevant_chunks_mock.side_effect = service_error

    response = client.post(
        f"/organizations/{uuid4()}/search",
        json={
            "query": "Projenin mimarisi nedir?",
            "limit": 5,
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
