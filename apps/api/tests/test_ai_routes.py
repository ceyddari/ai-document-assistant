from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.services import AiReadiness, AiReadinessError


@pytest.fixture
def settings() -> Settings:
    return Settings(
        postgres_db="test_database",
        postgres_user="test_user",
        postgres_password="test_password",
        postgres_host="localhost",
        postgres_port=5432,
        ollama_embedding_model="bge-m3",
        ollama_llm_model="qwen3:8b",
    )


@pytest.fixture
def check_ai_readiness_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr("app.api.routes.ai.check_ai_readiness", mock)
    return mock


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_ai_readiness_returns_models(
    client: TestClient,
    check_ai_readiness_mock: AsyncMock,
) -> None:
    check_ai_readiness_mock.return_value = AiReadiness(
        embedding_model="bge-m3",
        llm_model="qwen3:8b",
    )

    response = client.get("/ai/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "embedding_model": "bge-m3",
        "llm_model": "qwen3:8b",
    }
    check_ai_readiness_mock.assert_awaited_once()


def test_ai_readiness_returns_503_when_ai_is_unavailable(
    client: TestClient,
    check_ai_readiness_mock: AsyncMock,
) -> None:
    check_ai_readiness_mock.side_effect = AiReadinessError(
        "Gerekli Ollama modelleri bulunamadı: qwen3:8b."
    )

    response = client.get("/ai/readiness")

    assert response.status_code == 503
    assert response.json() == {"detail": "Gerekli Ollama modelleri bulunamadı: qwen3:8b."}
