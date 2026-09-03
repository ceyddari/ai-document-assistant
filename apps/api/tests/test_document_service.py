from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from app.core.config import Settings
from app.models import Organization
from app.services import (
    DocumentTooLargeError,
    InvalidPdfError,
    OrganizationNotFoundError,
    create_document,
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
