import asyncio
import logging
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import Document
from app.services import (
    DocumentProcessingError,
    EmbeddingService,
    process_document,
)
from app.services.llm_service import LlmService, LlmServiceError
from app.services.summary_service import list_unsummarized_documents, summarize_document

logger = logging.getLogger(__name__)

# One document at a time: parallel uploads would flood Ollama, and questions asked meanwhile
# would wait behind every queued embedding batch. Waiting documents stay "pending".
# shortcut: per process, like the rest of background processing; a job queue replaces it.
_processing_slot = asyncio.Semaphore(1)
# Separate slot: a long summary must not hold back the next upload's embeddings.
_summary_slot = asyncio.Semaphore(1)


async def process_document_in_background(document_id: UUID) -> None:
    # Acquired before opening a session, so queued documents hold no DB connection.
    async with _processing_slot:
        processed = await _process(document_id)
    if processed:
        await summarize_document_in_background(document_id)


async def summarize_document_in_background(document_id: UUID) -> None:
    settings = get_settings()
    if not settings.rag_section_summaries:
        return
    async with _summary_slot, get_session_factory()() as session:
        try:
            await summarize_document(
                document_id=document_id,
                session=session,
                llm_service=LlmService(settings=settings),
            )
        # Summaries are optional: the summary question falls back to sampled pages.
        except (LlmServiceError, SQLAlchemyError):
            await session.rollback()
            logger.exception("Doküman bölüm özetleri oluşturulamadı: %s", document_id)


async def summarize_missing_documents() -> None:
    """Fill in summaries for documents uploaded before they existed or interrupted midway."""
    if not get_settings().rag_section_summaries:
        return
    try:
        async with get_session_factory()() as session:
            document_ids = await list_unsummarized_documents(session=session)
    except (OSError, SQLAlchemyError):
        logger.exception("Özeti eksik dokümanlar listelenemedi.")
        return
    for document_id in document_ids:
        await summarize_document_in_background(document_id)


async def _process(document_id: UUID) -> bool:
    session_factory = get_session_factory()

    async with session_factory() as session:
        document = await session.get(Document, document_id)

        if document is None:
            logger.warning(
                "Arka planda işlenecek doküman bulunamadı: %s",
                document_id,
            )
            return False

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
            return False
        return True
