from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from app.core.config import Settings
from app.models import Document, DocumentStatus, Organization
from app.services import (
    DocumentNotFoundError,
    DocumentNotRetryableError,
    DocumentTooLargeError,
    InvalidPdfError,
    OrganizationNotFoundError,
    create_document,
    get_document_by_id,
    list_documents,
    prepare_document_retry,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        postgres_db="test_database",
        postgres_user="test_user",
        postgres_password="test_password",
        postgres_host="localhost",
        postgres_port=5432,
        storage_directory=tmp_path,
        max_upload_size_mb=1,
    )


@pytest.fixture
def db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def create_upload_file(
    *,
    content: bytes,
    filename: str = "document.pdf",
    content_type: str = "application/pdf",
) -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def build_document(
    *,
    organization_id: UUID,
    filename: str,
) -> Document:
    document_id = uuid4()

    return Document(
        id=document_id,
        organization_id=organization_id,
        original_filename=filename,
        stored_filename=f"{document_id}.pdf",
        storage_path=f"storage/documents/{document_id}.pdf",
        content_type="application/pdf",
        size_bytes=100,
        status=DocumentStatus.PENDING,
    )


@pytest.mark.asyncio
async def test_create_document_saves_valid_pdf(
    settings: Settings,
    db_session: AsyncMock,
) -> None:
    organization_id = uuid4()
    db_session.get.return_value = Organization(
        id=organization_id,
        name="Test Organization",
        slug="test-organization",
    )
    file = create_upload_file(
        content=b"%PDF-1.7\nTest PDF content",
    )

    document = await create_document(
        file=file,
        organization_id=organization_id,
        session=db_session,
        settings=settings,
    )

    saved_path = Path(document.storage_path)

    assert saved_path.exists()
    assert saved_path.read_bytes() == b"%PDF-1.7\nTest PDF content"
    assert document.original_filename == "document.pdf"
    assert document.organization_id == organization_id
    assert document.size_bytes == len(b"%PDF-1.7\nTest PDF content")
    db_session.add.assert_called_once_with(document)
    db_session.commit.assert_awaited_once()
    db_session.refresh.assert_awaited_once_with(document)


@pytest.mark.asyncio
async def test_create_document_rejects_invalid_pdf_content(
    settings: Settings,
    db_session: AsyncMock,
) -> None:
    organization_id = uuid4()
    db_session.get.return_value = Organization(
        id=organization_id,
        name="Test Organization",
        slug="test-organization",
    )
    file = create_upload_file(
        content=b"This is not a PDF",
    )

    with pytest.raises(InvalidPdfError, match="geçerli bir PDF değil"):
        await create_document(
            file=file,
            organization_id=organization_id,
            session=db_session,
            settings=settings,
        )

    assert list(settings.storage_directory.iterdir()) == []
    db_session.add.assert_not_called()
    db_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_document_rejects_file_over_size_limit(
    settings: Settings,
    db_session: AsyncMock,
) -> None:
    organization_id = uuid4()
    db_session.get.return_value = Organization(
        id=organization_id,
        name="Test Organization",
        slug="test-organization",
    )
    oversized_content = b"%PDF-" + b"x" * settings.max_upload_size_bytes
    file = create_upload_file(
        content=oversized_content,
    )

    with pytest.raises(DocumentTooLargeError, match="en fazla 1 MB"):
        await create_document(
            file=file,
            organization_id=organization_id,
            session=db_session,
            settings=settings,
        )

    assert list(settings.storage_directory.iterdir()) == []
    db_session.add.assert_not_called()
    db_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_document_rejects_unknown_organization(
    settings: Settings,
    db_session: AsyncMock,
) -> None:
    organization_id = uuid4()
    db_session.get.return_value = None
    file = create_upload_file(
        content=b"%PDF-1.7\nTest PDF content",
    )

    with pytest.raises(OrganizationNotFoundError, match="Organizasyon bulunamadı"):
        await create_document(
            file=file,
            organization_id=organization_id,
            session=db_session,
            settings=settings,
        )

    assert list(settings.storage_directory.iterdir()) == []
    db_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_list_documents_returns_paginated_organization_documents(
    db_session: AsyncMock,
) -> None:
    organization_id = uuid4()
    expected_documents = [
        build_document(
            organization_id=organization_id,
            filename="policy.pdf",
        ),
        build_document(
            organization_id=organization_id,
            filename="handbook.pdf",
        ),
    ]

    db_session.get.return_value = Organization(
        id=organization_id,
        name="Test Organization",
        slug="test-organization",
    )

    scalar_result = MagicMock()
    scalar_result.all.return_value = expected_documents

    db_session.scalars.return_value = scalar_result
    db_session.scalar.return_value = 2

    documents, total = await list_documents(
        organization_id=organization_id,
        session=db_session,
        limit=20,
        offset=0,
    )

    assert documents == expected_documents
    assert total == 2

    db_session.get.assert_awaited_once_with(
        Organization,
        organization_id,
    )
    db_session.scalars.assert_awaited_once()
    db_session.scalar.assert_awaited_once()

    documents_statement = db_session.scalars.await_args.args[0]
    count_statement = db_session.scalar.await_args.args[0]

    assert organization_id in documents_statement.compile().params.values()
    assert organization_id in count_statement.compile().params.values()


@pytest.mark.asyncio
async def test_list_documents_rejects_unknown_organization(
    db_session: AsyncMock,
) -> None:
    organization_id = uuid4()
    db_session.get.return_value = None

    with pytest.raises(
        OrganizationNotFoundError,
        match="Organizasyon bulunamadı",
    ):
        await list_documents(
            organization_id=organization_id,
            session=db_session,
            limit=20,
            offset=0,
        )

    db_session.scalars.assert_not_awaited()
    db_session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_document_by_id_returns_organization_document(
    db_session: AsyncMock,
) -> None:
    organization_id = uuid4()
    document = build_document(
        organization_id=organization_id,
        filename="policy.pdf",
    )
    db_session.scalar.return_value = document

    result = await get_document_by_id(
        organization_id=organization_id,
        document_id=document.id,
        session=db_session,
    )

    assert result is document
    db_session.scalar.assert_awaited_once()

    statement = db_session.scalar.await_args.args[0]
    statement_parameters = statement.compile().params.values()

    assert organization_id in statement_parameters
    assert document.id in statement_parameters


@pytest.mark.asyncio
async def test_get_document_by_id_rejects_missing_or_other_organization_document(
    db_session: AsyncMock,
) -> None:
    organization_id = uuid4()
    document_id = uuid4()
    db_session.scalar.return_value = None

    with pytest.raises(
        DocumentNotFoundError,
        match="Doküman bulunamadı",
    ):
        await get_document_by_id(
            organization_id=organization_id,
            document_id=document_id,
            session=db_session,
        )

    db_session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_document_retry_resets_failed_document(
    db_session: AsyncMock,
) -> None:
    organization_id = uuid4()
    document = build_document(organization_id=organization_id, filename="policy.pdf")
    document.status = DocumentStatus.FAILED
    document.error_message = "Embedding failed"
    db_session.scalar.return_value = document

    result = await prepare_document_retry(
        organization_id=organization_id,
        document_id=document.id,
        session=db_session,
    )

    assert result is document
    assert document.status == DocumentStatus.PENDING
    assert document.error_message is None
    db_session.commit.assert_awaited_once()
    db_session.refresh.assert_awaited_once_with(document)


@pytest.mark.asyncio
async def test_prepare_document_retry_rejects_active_document(
    db_session: AsyncMock,
) -> None:
    document = build_document(organization_id=uuid4(), filename="policy.pdf")
    document.status = DocumentStatus.PROCESSING
    db_session.scalar.return_value = document

    with pytest.raises(DocumentNotRetryableError, match="Yalnızca işlenemeyen"):
        await prepare_document_retry(
            organization_id=document.organization_id,
            document_id=document.id,
            session=db_session,
        )

    db_session.commit.assert_not_awaited()
