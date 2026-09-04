import asyncio
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentStatus
from app.services.pdf_parser import (
    ParsedPage,
    PdfParsingError,
    parse_pdf,
)


class DocumentProcessingError(Exception):
    pass


async def process_document(
    *,
    document: Document,
    session: AsyncSession,
) -> list[ParsedPage]:
    document.status = DocumentStatus.PROCESSING
    document.error_message = None

    try:
        await session.commit()

        pages = await asyncio.to_thread(
            parse_pdf,
            Path(document.storage_path),
        )

        document.status = DocumentStatus.READY
        await session.commit()
        await session.refresh(document)

        return pages

    except PdfParsingError as error:
        await session.rollback()

        document.status = DocumentStatus.FAILED
        document.error_message = str(error)

        try:
            await session.commit()
            await session.refresh(document)
        except SQLAlchemyError as database_error:
            await session.rollback()
            raise DocumentProcessingError(
                "Doküman işleme hatası kaydedilemedi."
            ) from database_error

        raise DocumentProcessingError("Doküman işlenemedi.") from error

    except SQLAlchemyError as error:
        await session.rollback()
        raise DocumentProcessingError("Doküman durumu güncellenemedi.") from error
