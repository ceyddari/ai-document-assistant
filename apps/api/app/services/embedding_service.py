import asyncio

from langchain_ollama import OllamaEmbeddings

from app.core.config import Settings
from app.models import EMBEDDING_DIMENSIONS


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

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        try:
            async with asyncio.timeout(self._timeout_seconds):
                embeddings = await self._model.aembed_documents(texts)
        except TimeoutError as error:
            raise EmbeddingServiceError("Doküman embedding isteği zaman aşımına uğradı.") from error
        except Exception as error:
            raise EmbeddingServiceError("Doküman embedding'leri üretilemedi.") from error

        if len(embeddings) != len(texts):
            raise EmbeddingServiceError("Embedding sayısı metin sayısıyla eşleşmiyor.")

        self._validate_dimensions(embeddings)

        return embeddings

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
