from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.services import AiReadinessError, check_ai_readiness


@pytest.fixture
def settings() -> Settings:
    return Settings(
        postgres_db="test_database",
        postgres_user="test_user",
        postgres_password="test_password",
        postgres_host="localhost",
        postgres_port=5432,
        ollama_base_url="http://localhost:11434/",
        ollama_embedding_model="bge-m3",
        ollama_llm_model="qwen3:8b",
    )


@pytest.fixture
def http_client() -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    context_manager = AsyncMock()
    context_manager.__aenter__.return_value = client

    with patch(
        "app.services.ai_readiness_service.httpx.AsyncClient",
        return_value=context_manager,
    ):
        yield client


@pytest.mark.asyncio
async def test_check_ai_readiness_accepts_required_models(
    settings: Settings,
    http_client: AsyncMock,
) -> None:
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = {
        "models": [
            {"name": "bge-m3:latest", "model": "bge-m3:latest"},
            {"name": "qwen3:8b", "model": "qwen3:8b"},
        ]
    }
    http_client.get.return_value = response

    readiness = await check_ai_readiness(settings=settings)

    assert readiness.embedding_model == "bge-m3"
    assert readiness.llm_model == "qwen3:8b"
    http_client.get.assert_awaited_once_with("http://localhost:11434/api/tags")
    response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_check_ai_readiness_rejects_missing_model(
    settings: Settings,
    http_client: AsyncMock,
) -> None:
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = {
        "models": [{"name": "bge-m3:latest"}],
    }
    http_client.get.return_value = response

    with pytest.raises(AiReadinessError, match="qwen3:8b"):
        await check_ai_readiness(settings=settings)


@pytest.mark.asyncio
async def test_check_ai_readiness_wraps_http_error(
    settings: Settings,
    http_client: AsyncMock,
) -> None:
    http_client.get.side_effect = httpx.ConnectError("Ollama unavailable")

    with pytest.raises(AiReadinessError, match="Ollama servisine erişilemiyor"):
        await check_ai_readiness(settings=settings)


@pytest.mark.asyncio
async def test_check_ai_readiness_rejects_invalid_payload(
    settings: Settings,
    http_client: AsyncMock,
) -> None:
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = {"models": "invalid"}
    http_client.get.return_value = response

    with pytest.raises(AiReadinessError, match="model listesi okunamadı"):
        await check_ai_readiness(settings=settings)
