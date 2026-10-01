import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.services import LlmService, LlmServiceError


@pytest.fixture
def settings() -> Settings:
    return Settings(
        postgres_db="test_database",
        postgres_user="test_user",
        postgres_password="test_password",
        postgres_host="localhost",
        postgres_port=5432,
        ollama_base_url="http://localhost:11434",
        ollama_llm_model="qwen3:8b",
    )


@pytest.fixture
def model() -> MagicMock:
    with patch("app.services.llm_service.ChatOllama") as model_constructor:
        model = MagicMock()
        model.ainvoke = AsyncMock()
        model_constructor.return_value = model
        yield model


@pytest.mark.asyncio
async def test_generate_answer_returns_trimmed_content(
    settings: Settings,
    model: MagicMock,
) -> None:
    model.ainvoke.return_value = MagicMock(content="  Kaynaklara dayalı cevap.  ")
    service = LlmService(settings=settings)

    answer = await service.generate_answer(
        system_prompt="Sistem talimatı",
        user_prompt="Kullanıcı sorusu",
    )

    assert answer == "Kaynaklara dayalı cevap."
    model.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_answer_rejects_empty_content(
    settings: Settings,
    model: MagicMock,
) -> None:
    model.ainvoke.return_value = MagicMock(content="   ")
    service = LlmService(settings=settings)

    with pytest.raises(LlmServiceError, match="boş bir cevap"):
        await service.generate_answer(
            system_prompt="Sistem talimatı",
            user_prompt="Kullanıcı sorusu",
        )


@pytest.mark.asyncio
async def test_generate_answer_wraps_model_error(
    settings: Settings,
    model: MagicMock,
) -> None:
    model.ainvoke.side_effect = RuntimeError("Ollama unavailable")
    service = LlmService(settings=settings)

    with pytest.raises(LlmServiceError, match="cevap üretemedi"):
        await service.generate_answer(
            system_prompt="Sistem talimatı",
            user_prompt="Kullanıcı sorusu",
        )


@pytest.mark.asyncio
async def test_generate_answer_wraps_timeout(
    settings: Settings,
    model: MagicMock,
) -> None:
    settings.ollama_timeout_seconds = 0.001

    async def slow_response(_: object) -> MagicMock:
        await asyncio.sleep(0.05)
        return MagicMock(content="Geç cevap")

    model.ainvoke.side_effect = slow_response
    service = LlmService(settings=settings)

    with pytest.raises(LlmServiceError, match="zaman aşımına uğradı"):
        await service.generate_answer(
            system_prompt="Sistem talimatı",
            user_prompt="Kullanıcı sorusu",
        )
