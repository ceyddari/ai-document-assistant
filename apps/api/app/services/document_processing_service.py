import asyncio
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocumentStatus
from app.services.embedding_service import (
    EmbeddingService,
    EmbeddingServiceError,
)
from app.services.pdf_parser import PdfParsingError, parse_pdf
from app.services.text_chunker import chunk_pages


class DocumentProcessingError(Exception):
    pass


class EmptyDocumentError(Exception):
    pass


async def _mark_document_failed(
    *,
    document: Document,
    session: AsyncSession,
    error_message: str,
) -> None:
    await session.rollback()
    document.status = DocumentStatus.FAILED
    document.error_message = error_message

    try:
        await session.commit()
        await session.refresh(document)
    except SQLAlchemyError as database_error:
        await session.rollback()
        raise DocumentProcessingError(
            "Doküman işleme hatası kaydedilemedi."
        ) from database_error


async def process_document(
    *,
    document: Document,
    session: AsyncSession,
    embedding_service: EmbeddingService,
) -> list[DocumentChunk]:
    document.status = DocumentStatus.PROCESSING
    document.error_message = None

    try:
        await session.commit()

        pages = await asyncio.to_thread(
            parse_pdf,
            Path(document.storage_path),
        )

        text_chunks = chunk_pages(pages)

        if not text_chunks:
            raise EmptyDocumentError("Dokümanda işlenebilir metin bulunamadı.")

        embeddings = await embedding_service.embed_documents(
            [chunk.content for chunk in text_chunks]
        )

        document_chunks = [
            DocumentChunk(
                organization_id=document.organization_id,
                document_id=document.id,
                page_number=text_chunk.page_number,
                chunk_index=text_chunk.chunk_index,
                content=text_chunk.content,
                embedding=embedding,
            )
            for text_chunk, embedding in zip(
                text_chunks,
                embeddings,
                strict=True,
            )
        ]

        session.add_all(document_chunks)

        document.status = DocumentStatus.READY

        await session.commit()
        await session.refresh(document)

        return document_chunks

    except (
        PdfParsingError,
        EmptyDocumentError,
        EmbeddingServiceError,
    ) as error:
        await _mark_document_failed(
            document=document,
            session=session,
            error_message=str(error),
        )
        raise DocumentProcessingError("Doküman işlenemedi.") from error

    except SQLAlchemyError as error:
        await session.rollback()
        raise DocumentProcessingError("Doküman durumu güncellenemedi.") from error

    except Exception as error:
        await _mark_document_failed(
            document=document,
            session=session,
            error_message="Doküman işlenirken beklenmeyen bir hata oluştu.",
        )
        raise DocumentProcessingError("Doküman işlenemedi.") from error
