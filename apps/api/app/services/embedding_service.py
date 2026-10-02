import asyncio
import logging

import httpx
from langchain_ollama import OllamaEmbeddings

from app.core.config import Settings
from app.models import EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)


class EmbeddingServiceError(Exception):
    pass


class EmbeddingDimensionError(EmbeddingServiceError):
    pass


class EmbeddingService:
    def __init__(
        self,
        *,
        settings: Settings,
    ) -> None:
        self._model = OllamaEmbeddings(
            model=settings.ollama_embedding_model,
            base_url=settings.ollama_base_url,
        )
        self._timeout_seconds = settings.ollama_timeout_seconds
        self._batch_size = settings.ollama_embedding_batch_size
        self._max_retries = settings.ollama_embedding_max_retries
        self._retry_delay_seconds = settings.ollama_embedding_retry_delay_seconds

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        embeddings: list[list[float]] = []
        total_batches = (len(texts) + self._batch_size - 1) // self._batch_size

        for batch_index, start in enumerate(
            range(0, len(texts), self._batch_size),
            start=1,
        ):
            batch = texts[start : start + self._batch_size]
            batch_embeddings = await self._embed_document_batch(
                batch=batch,
                batch_index=batch_index,
                total_batches=total_batches,
            )

            if len(batch_embeddings) != len(batch):
                raise EmbeddingServiceError(
                    "Embedding sayısı metin sayısıyla eşleşmiyor "
                    f"(batch {batch_index}/{total_batches})."
                )

            self._validate_dimensions(batch_embeddings)
            embeddings.extend(batch_embeddings)

        return embeddings

    async def _embed_document_batch(
        self,
        *,
        batch: list[str],
        batch_index: int,
        total_batches: int,
    ) -> list[list[float]]:
        for attempt in range(self._max_retries + 1):
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    return await self._model.aembed_documents(batch)
            except Exception as error:
                if attempt >= self._max_retries or not self._is_retryable(error):
                    message = (
                        "Doküman embedding isteği zaman aşımına uğradı."
                        if isinstance(error, TimeoutError)
                        else "Doküman embedding'leri üretilemedi."
                    )
                    raise EmbeddingServiceError(
                        f"{message} Batch {batch_index}/{total_batches}."
                    ) from error

                delay = self._retry_delay_seconds * (2**attempt)
                logger.warning(
                    "Embedding batch yeniden denenecek: batch=%s/%s attempt=%s/%s "
                    "delay=%s error_type=%s",
                    batch_index,
                    total_batches,
                    attempt + 1,
                    self._max_retries + 1,
                    delay,
                    type(error).__name__,
                )
                if delay:
                    await asyncio.sleep(delay)

        raise RuntimeError("Embedding retry döngüsü beklenmedik şekilde tamamlandı.")

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        if isinstance(error, (TimeoutError, ConnectionError, httpx.TransportError)):
            return True

        status_code = getattr(error, "status_code", None)
        return isinstance(status_code, int) and (
            status_code == -1 or status_code in {408, 429} or status_code >= 500
        )

    async def embed_query(
        self,
        query: str,
    ) -> list[float]:
        if not query.strip():
            raise ValueError("Soru boş olamaz.")

        try:
            async with asyncio.timeout(self._timeout_seconds):
                embedding = await self._model.aembed_query(query)
        except TimeoutError as error:
            raise EmbeddingServiceError("Soru embedding isteği zaman aşımına uğradı.") from error
        except Exception as error:
            raise EmbeddingServiceError("Soru embedding'i üretilemedi.") from error

        self._validate_dimensions([embedding])

        return embedding

    @staticmethod
    def _validate_dimensions(
        embeddings: list[list[float]],
    ) -> None:
        invalid_dimensions = {
            len(embedding) for embedding in embeddings if len(embedding) != EMBEDDING_DIMENSIONS
        }

        if invalid_dimensions:
            raise EmbeddingDimensionError(
                "Embedding boyutu "
                f"{EMBEDDING_DIMENSIONS} olmalıdır; "
                f"alınan boyutlar: {sorted(invalid_dimensions)}."
            )
