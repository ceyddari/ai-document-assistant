import asyncio
import logging
from uuid import UUID

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import Document
from app.services import (
    DocumentProcessingError,
    EmbeddingService,
    process_document,
)

logger = logging.getLogger(__name__)

# One document at a time: parallel uploads would flood Ollama, and questions asked meanwhile
# would wait behind every queued embedding batch. Waiting documents stay "pending".
# shortcut: per process, like the rest of background processing; a job queue replaces it.
_processing_slot = asyncio.Semaphore(1)


async def process_document_in_background(document_id: UUID) -> None:
    # Acquired before opening a session, so queued documents hold no DB connection.
    async with _processing_slot:
        await _process(document_id)


async def _process(document_id: UUID) -> None:
    session_factory = get_session_factory()

    async with session_factory() as session:
        document = await session.get(Document, document_id)

        if document is None:
            logger.warning(
                "Arka planda işlenecek doküman bulunamadı: %s",
                document_id,
            )
            return

        settings = get_settings()
        embedding_service = EmbeddingService(settings=settings)

        try:
            await process_document(
                document=document,
                session=session,
                embedding_service=embedding_service,
            )
        except DocumentProcessingError:
            logger.exception(
                "Doküman arka planda işlenemedi: %s",
                document_id,
            )
