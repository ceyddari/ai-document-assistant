import hashlib
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
from fastapi import UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Document, DocumentStatus, Organization
from app.services.folder_service import get_folder

UPLOAD_CHUNK_SIZE = 1024 * 1024
PDF_SIGNATURE = b"%PDF-"
INTERRUPTED_PROCESSING_MESSAGE = (
    "Sunucu yeniden başladığı için işleme yarıda kaldı. Yeniden deneyebilirsiniz."
)


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


class DocumentBusyError(Exception):
    pass


class DuplicateDocumentError(Exception):
    pass


DUPLICATE_CONSTRAINT = "uq_documents_org_content_sha256"


def _duplicate_error(existing_filename: str | None) -> DuplicateDocumentError:
    if existing_filename:
        return DuplicateDocumentError(f"Bu doküman zaten yüklü: {existing_filename}")
    return DuplicateDocumentError("Bu doküman zaten yüklü.")


async def _find_duplicate_filename(
    *, organization_id: UUID, content_sha256: str, session: AsyncSession
) -> str | None:
    return await session.scalar(
        select(Document.original_filename).where(
            Document.organization_id == organization_id,
            Document.content_sha256 == content_sha256,
        )
    )


async def create_document(
    *,
    file: UploadFile,
    organization_id: UUID,
    session: AsyncSession,
    settings: Settings,
    folder_id: UUID | None = None,
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

    if folder_id is not None:
        await get_folder(organization_id=organization_id, folder_id=folder_id, session=session)

    settings.storage_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    stored_filename = f"{uuid4()}.pdf"
    storage_path = settings.storage_directory / stored_filename
    size_bytes = 0
    first_chunk = True
    digest = hashlib.sha256()

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

                digest.update(chunk)
                await destination.write(chunk)

        if size_bytes == 0:
            raise InvalidPdfError("Boş bir PDF yüklenemez.")

        content_sha256 = digest.hexdigest()
        duplicate_filename = await _find_duplicate_filename(
            organization_id=organization_id, content_sha256=content_sha256, session=session
        )
        if duplicate_filename is not None:
            raise _duplicate_error(duplicate_filename)

    except Exception:
        storage_path.unlink(missing_ok=True)
        raise

    finally:
        await file.close()

    document = Document(
        organization_id=organization_id,
        folder_id=folder_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        storage_path=storage_path.as_posix(),
        content_type=file.content_type,
        size_bytes=size_bytes,
        content_sha256=content_sha256,
    )

    session.add(document)

    try:
        await session.commit()
        await session.refresh(document)

    except SQLAlchemyError as error:
        await session.rollback()
        storage_path.unlink(missing_ok=True)
        # Two identical uploads raced past the check above; the unique constraint caught the loser.
        if isinstance(error, IntegrityError) and DUPLICATE_CONSTRAINT in str(error):
            existing = await _find_duplicate_filename(
                organization_id=organization_id, content_sha256=content_sha256, session=session
            )
            raise _duplicate_error(existing) from error
        raise

    return document


async def list_documents(
    *,
    organization_id: UUID,
    session: AsyncSession,
    limit: int,
    offset: int,
    folder_id: UUID | None = None,
) -> tuple[Sequence[Document], int]:
    organization = await session.get(Organization, organization_id)

    if organization is None:
        raise OrganizationNotFoundError("Organizasyon bulunamadı.")

    filters = [Document.organization_id == organization_id]
    if folder_id is not None:
        filters.append(Document.folder_id == folder_id)

    documents_statement = (
        select(Document)
        .where(*filters)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    count_statement = select(func.count()).select_from(Document).where(*filters)

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


async def fail_interrupted_documents(*, session: AsyncSession) -> int:
    # shortcut: assumes a single API process; with several workers or replicas this would
    # fail another process's in-flight job. Move processing to a job queue before scaling out.
    statement = (
        update(Document)
        .where(Document.status.in_([DocumentStatus.PENDING, DocumentStatus.PROCESSING]))
        .values(status=DocumentStatus.FAILED, error_message=INTERRUPTED_PROCESSING_MESSAGE)
    )

    try:
        result = await session.execute(statement)
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    return result.rowcount


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
        raise DocumentNotRetryableError("Yalnızca işlenemeyen dokümanlar yeniden işlenebilir.")

    document.status = DocumentStatus.PENDING
    document.error_message = None

    try:
        await session.commit()
        await session.refresh(document)
    except SQLAlchemyError:
        await session.rollback()
        raise

    return document


def resolve_document_file(*, document: Document, settings: Settings) -> Path:
    """Stored file path, refused if it points outside the storage directory."""
    storage_root = settings.storage_directory.resolve()
    path = Path(document.storage_path).resolve()

    # storage_path is written by the server, but a bad row must never expose other files.
    if not path.is_relative_to(storage_root) or not path.is_file():
        raise DocumentNotFoundError("Doküman dosyası bulunamadı.")

    return path


async def delete_document(
    *,
    organization_id: UUID,
    document_id: UUID,
    session: AsyncSession,
) -> Path:
    """Delete the row (its chunks and the sources citing them cascade); return its file path.

    The caller removes the file only after this commit, so a failed commit never leaves a
    row pointing at a missing file.
    """
    # Row lock: serializes with prepare_document_retry, which locks the same row.
    document = await session.scalar(
        select(Document)
        .where(
            Document.id == document_id,
            Document.organization_id == organization_id,
        )
        .with_for_update()
    )

    if document is None:
        raise DocumentNotFoundError("Doküman bulunamadı.")

    if document.status in (DocumentStatus.PENDING, DocumentStatus.PROCESSING):
        await session.rollback()
        raise DocumentBusyError("İşlenmekte olan doküman silinemez; işlem bitince tekrar deneyin.")

    storage_path = Path(document.storage_path)

    try:
        await session.delete(document)
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    return storage_path
