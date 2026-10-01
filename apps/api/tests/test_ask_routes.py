from collections.abc import AsyncIterator, Iterator
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
    LlmServiceError,
    OrganizationNotFoundError,
    RagAnswer,
    RetrievedChunk,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        postgres_db="test_database",
        postgres_user="test_user",
        postgres_password="test_password",
        postgres_host="localhost",
        postgres_port=5432,
        ollama_base_url="http://localhost:11434",
        ollama_embedding_model="bge-m3",
        ollama_llm_model="qwen3:8b",
    )


@pytest.fixture
def db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    embedding_service = MagicMock()
    llm_service = MagicMock()
    monkeypatch.setattr(
        "app.api.routes.ask.EmbeddingService",
        MagicMock(return_value=embedding_service),
    )
    monkeypatch.setattr(
        "app.api.routes.ask.LlmService",
        MagicMock(return_value=llm_service),
    )
    return embedding_service, llm_service


@pytest.fixture
def answer_question_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr("app.api.routes.ask.answer_question", mock)
    return mock


@pytest.fixture
def client(db_session: AsyncMock, settings: Settings) -> Iterator[TestClient]:
    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_ask_returns_answer_with_sources(
    client: TestClient,
    db_session: AsyncMock,
    services: tuple[MagicMock, MagicMock],
    answer_question_mock: AsyncMock,
) -> None:
    organization_id = uuid4()
    source = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="policy.pdf",
        page_number=2,
        content="Yıllık izin talebi sistemden oluşturulur.",
        similarity=0.82,
    )
    answer_question_mock.return_value = RagAnswer(
        answer="İzin talebi sistemden oluşturulur. [Kaynak 1]",
        sources=[source],
    )

    response = client.post(
        f"/organizations/{organization_id}/ask",
        json={"question": "  Yıllık izin nasıl alınır?  ", "limit": 4},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "İzin talebi sistemden oluşturulur. [Kaynak 1]"
    assert response.json()["sources"][0]["chunk_id"] == str(source.chunk_id)
    answer_question_mock.assert_awaited_once_with(
        organization_id=organization_id,
        question="Yıllık izin nasıl alınır?",
        session=db_session,
        embedding_service=services[0],
        llm_service=services[1],
        limit=4,
        minimum_similarity=0.35,
    )


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
            LlmServiceError("Ollama unavailable"),
            503,
            "Dil modeli servisine şu anda erişilemiyor.",
        ),
        (
            SQLAlchemyError("Database unavailable"),
            503,
            "Soru şu anda yanıtlanamıyor.",
        ),
    ],
)
def test_ask_maps_service_errors(
    client: TestClient,
    services: tuple[MagicMock, MagicMock],
    answer_question_mock: AsyncMock,
    service_error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    answer_question_mock.side_effect = service_error

    response = client.post(
        f"/organizations/{uuid4()}/ask",
        json={"question": "Yıllık izin nasıl alınır?"},
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


def test_ask_rejects_blank_question(
    client: TestClient,
    services: tuple[MagicMock, MagicMock],
    answer_question_mock: AsyncMock,
) -> None:
    response = client.post(
        f"/organizations/{uuid4()}/ask",
        json={"question": "   "},
    )

    assert response.status_code == 422
    answer_question_mock.assert_not_awaited()
