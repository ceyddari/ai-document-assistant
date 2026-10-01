from dataclasses import dataclass

import httpx

from app.core.config import Settings


class AiReadinessError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AiReadiness:
    embedding_model: str
    llm_model: str


def _model_is_available(model: str, available_models: set[str]) -> bool:
    if model in available_models:
        return True

    if ":" not in model:
        return f"{model}:latest" in available_models

    return False


async def check_ai_readiness(*, settings: Settings) -> AiReadiness:
    tags_url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"

    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
            response = await client.get(tags_url)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as error:
        raise AiReadinessError("Ollama servisine erişilemiyor.") from error

    models = payload.get("models")

    if not isinstance(models, list):
        raise AiReadinessError("Ollama model listesi okunamadı.")

    available_models = {
        value
        for model_data in models
        if isinstance(model_data, dict)
        for key in ("name", "model")
        if isinstance((value := model_data.get(key)), str)
    }

    missing_models = [
        model
        for model in (
            settings.ollama_embedding_model,
            settings.ollama_llm_model,
        )
        if not _model_is_available(model, available_models)
    ]

    if missing_models:
        raise AiReadinessError(f"Gerekli Ollama modelleri bulunamadı: {', '.join(missing_models)}.")

    return AiReadiness(
        embedding_model=settings.ollama_embedding_model,
        llm_model=settings.ollama_llm_model,
    )
