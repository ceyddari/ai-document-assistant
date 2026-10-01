import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.models import EMBEDDING_DIMENSIONS
from app.services import (
    EmbeddingDimensionError,
    EmbeddingService,
    EmbeddingServiceError,
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
    )


@pytest.fixture
def embedding_model() -> Iterator[MagicMock]:
    with patch("app.services.embedding_service.OllamaEmbeddings") as model_constructor:
        model = MagicMock()
        model.aembed_documents = AsyncMock()
        model.aembed_query = AsyncMock()
        model_constructor.return_value = model

        yield model


@pytest.fixture
def embedding_service(
    settings: Settings,
    embedding_model: MagicMock,
) -> EmbeddingService:
    return EmbeddingService(settings=settings)


@pytest.mark.asyncio
async def test_embed_documents_returns_embeddings(
    embedding_service: EmbeddingService,
    embedding_model: MagicMock,
) -> None:
    texts = [
        "Yıllık izin prosedürü.",
        "Satın alma prosedürü.",
    ]
    expected_embeddings = [
        [0.1] * EMBEDDING_DIMENSIONS,
        [0.2] * EMBEDDING_DIMENSIONS,
    ]
    embedding_model.aembed_documents.return_value = expected_embeddings

    embeddings = await embedding_service.embed_documents(texts)

    assert embeddings == expected_embeddings
    embedding_model.aembed_documents.assert_awaited_once_with(texts)


@pytest.mark.asyncio
async def test_embed_documents_returns_empty_list_without_calling_model(
    embedding_service: EmbeddingService,
    embedding_model: MagicMock,
) -> None:
    embeddings = await embedding_service.embed_documents([])

    assert embeddings == []
    embedding_model.aembed_documents.assert_not_awaited()


@pytest.mark.asyncio
async def test_embed_documents_rejects_mismatched_embedding_count(
    embedding_service: EmbeddingService,
    embedding_model: MagicMock,
) -> None:
    embedding_model.aembed_documents.return_value = [[0.1] * EMBEDDING_DIMENSIONS]

    with pytest.raises(
        EmbeddingServiceError,
        match="Embedding sayısı metin sayısıyla eşleşmiyor",
    ):
        await embedding_service.embed_documents(
            [
                "Birinci metin",
                "İkinci metin",
            ]
        )


@pytest.mark.asyncio
async def test_embed_documents_rejects_invalid_embedding_dimension(
    embedding_service: EmbeddingService,
    embedding_model: MagicMock,
) -> None:
    embedding_model.aembed_documents.return_value = [[0.1, 0.2, 0.3]]

    with pytest.raises(
        EmbeddingDimensionError,
        match="Embedding boyutu 1024 olmalıdır",
    ):
        await embedding_service.embed_documents(["Yıllık izin prosedürü."])


@pytest.mark.asyncio
async def test_embed_query_returns_embedding(
    embedding_service: EmbeddingService,
    embedding_model: MagicMock,
) -> None:
    query = "Yıllık izin nasıl alınır?"
    expected_embedding = [0.1] * EMBEDDING_DIMENSIONS
    embedding_model.aembed_query.return_value = expected_embedding

    embedding = await embedding_service.embed_query(query)

    assert embedding == expected_embedding
    embedding_model.aembed_query.assert_awaited_once_with(query)


@pytest.mark.asyncio
async def test_embed_query_rejects_blank_query(
    embedding_service: EmbeddingService,
    embedding_model: MagicMock,
) -> None:
    with pytest.raises(
        ValueError,
        match="Soru boş olamaz",
    ):
        await embedding_service.embed_query("   ")

    embedding_model.aembed_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_embed_documents_wraps_model_error(
    embedding_service: EmbeddingService,
    embedding_model: MagicMock,
) -> None:
    embedding_model.aembed_documents.side_effect = RuntimeError("Ollama unavailable")

    with pytest.raises(
        EmbeddingServiceError,
        match="Doküman embedding'leri üretilemedi",
    ):
        await embedding_service.embed_documents(["Yıllık izin prosedürü."])


@pytest.mark.asyncio
async def test_embed_query_wraps_timeout(
    settings: Settings,
    embedding_model: MagicMock,
) -> None:
    settings.ollama_timeout_seconds = 0.001

    async def slow_embedding(_: str) -> list[float]:
        await asyncio.sleep(0.05)
        return [0.1] * EMBEDDING_DIMENSIONS

    embedding_model.aembed_query.side_effect = slow_embedding
    service = EmbeddingService(settings=settings)

    with pytest.raises(EmbeddingServiceError, match="zaman aşımına uğradı"):
        await service.embed_query("Yıllık izin nasıl alınır?")
