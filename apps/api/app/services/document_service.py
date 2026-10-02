from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Document, DocumentStatus, Organization

UPLOAD_CHUNK_SIZE = 1024 * 1024
PDF_SIGNATURE = b"%PDF-"


class OrganizationNotFoundError(Exception):
    pass


class InvalidPdfError(Exception):
    pass


class DocumentTooLargeError(Exception):
    pass


class DocumentNotFoundError(Exception):
    pass


class DocumentNotRetryableError(Exception):
    pass


async def create_document(
    *,
    file: UploadFile,
    organization_id: UUID,
    session: AsyncSession,
    settings: Settings,
) -> Document:
    original_filename = Path(file.filename or "").name

    if not original_filename:
        raise InvalidPdfError("Dosya adı bulunamadı.")

    if Path(original_filename).suffix.lower() != ".pdf":
        raise InvalidPdfError("Yalnızca PDF dosyaları yüklenebilir.")

    if file.content_type != "application/pdf":
        raise InvalidPdfError("Dosyanın içerik türü application/pdf olmalıdır.")

    organization = await session.get(Organization, organization_id)

    if organization is None:
        raise OrganizationNotFoundError("Organizasyon bulunamadı.")

    settings.storage_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    stored_filename = f"{uuid4()}.pdf"
    storage_path = settings.storage_directory / stored_filename
    size_bytes = 0
    first_chunk = True

    try:
        async with aiofiles.open(storage_path, "wb") as destination:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                if first_chunk:
                    if not chunk.startswith(PDF_SIGNATURE):
                        raise InvalidPdfError("Dosya geçerli bir PDF değil.")

                    first_chunk = False

                size_bytes += len(chunk)

                if size_bytes > settings.max_upload_size_bytes:
                    raise DocumentTooLargeError(
                        f"Dosya en fazla {settings.max_upload_size_mb} MB olabilir."
                    )

                await destination.write(chunk)

        if size_bytes == 0:
            raise InvalidPdfError("Boş bir PDF yüklenemez.")

    except Exception:
        storage_path.unlink(missing_ok=True)
        raise

    finally:
        await file.close()

    document = Document(
        organization_id=organization_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        storage_path=storage_path.as_posix(),
        content_type=file.content_type,
        size_bytes=size_bytes,
    )

    session.add(document)

    try:
        await session.commit()
        await session.refresh(document)

    except SQLAlchemyError:
        await session.rollback()
        storage_path.unlink(missing_ok=True)
        raise

    return document


async def list_documents(
    *,
    organization_id: UUID,
    session: AsyncSession,
    limit: int,
    offset: int,
) -> tuple[Sequence[Document], int]:
    organization = await session.get(Organization, organization_id)

    if organization is None:
        raise OrganizationNotFoundError("Organizasyon bulunamadı.")

    documents_statement = (
        select(Document)
        .where(Document.organization_id == organization_id)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    count_statement = (
        select(func.count())
        .select_from(Document)
        .where(Document.organization_id == organization_id)
    )

    documents = await session.scalars(documents_statement)
    total = await session.scalar(count_statement)

    return documents.all(), int(total or 0)


async def get_document_by_id(
    *,
    organization_id: UUID,
    document_id: UUID,
    session: AsyncSession,
) -> Document:
    statement = select(Document).where(
        Document.id == document_id,
        Document.organization_id == organization_id,
    )

    document = await session.scalar(statement)

    if document is None:
        raise DocumentNotFoundError("Doküman bulunamadı.")

    return document


async def prepare_document_retry(
    *,
    organization_id: UUID,
    document_id: UUID,
    session: AsyncSession,
) -> Document:
    statement = (
        select(Document)
        .where(
            Document.id == document_id,
            Document.organization_id == organization_id,
        )
        .with_for_update()
    )
    document = await session.scalar(statement)

    if document is None:
        raise DocumentNotFoundError("Doküman bulunamadı.")

    if document.status != DocumentStatus.FAILED:
        raise DocumentNotRetryableError(
            "Yalnızca işlenemeyen dokümanlar yeniden işlenebilir."
        )

    document.status = DocumentStatus.PENDING
    document.error_message = None

    try:
        await session.commit()
        await session.refresh(document)
    except SQLAlchemyError:
        await session.rollback()
        raise

    return document
