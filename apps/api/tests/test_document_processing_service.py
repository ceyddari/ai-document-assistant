from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentStatus
from app.services import (
    DocumentProcessingError,
    ParsedPage,
    PdfParsingError,
    process_document,
)


@pytest.fixture
def db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def build_document(tmp_path: Path) -> Document:
    document_id = uuid4()

    return Document(
        id=document_id,
        organization_id=uuid4(),
        original_filename="policy.pdf",
        stored_filename=f"{document_id}.pdf",
        storage_path=(tmp_path / f"{document_id}.pdf").as_posix(),
        content_type="application/pdf",
        size_bytes=100,
        status=DocumentStatus.PENDING,
    )


@pytest.mark.asyncio
async def test_process_document_marks_document_as_ready(
    tmp_path: Path,
    db_session: AsyncMock,
) -> None:
    document = build_document(tmp_path)
    expected_pages = [
        ParsedPage(
            page_number=1,
            text="First page content",
        ),
        ParsedPage(
            page_number=2,
            text="Second page content",
        ),
    ]

    with patch(
        "app.services.document_processing_service.parse_pdf",
        return_value=expected_pages,
    ) as parse_pdf_mock:
        pages = await process_document(
            document=document,
            session=db_session,
        )

    assert pages == expected_pages
    assert document.status == DocumentStatus.READY
    assert document.error_message is None

    parse_pdf_mock.assert_called_once_with(
        Path(document.storage_path),
    )
    assert db_session.commit.await_count == 2
    db_session.rollback.assert_not_awaited()
    db_session.refresh.assert_awaited_once_with(document)


@pytest.mark.asyncio
async def test_process_document_marks_document_as_failed_when_pdf_cannot_be_parsed(
    tmp_path: Path,
    db_session: AsyncMock,
) -> None:
    document = build_document(tmp_path)

    with (
        patch(
            "app.services.document_processing_service.parse_pdf",
            side_effect=PdfParsingError("PDF dosyası okunamadı."),
        ),
        pytest.raises(
            DocumentProcessingError,
            match="Doküman işlenemedi",
        ),
    ):
        await process_document(
            document=document,
            session=db_session,
        )

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "PDF dosyası okunamadı."
    assert db_session.commit.await_count == 2
    db_session.rollback.assert_awaited_once()
    db_session.refresh.assert_awaited_once_with(document)


@pytest.mark.asyncio
async def test_process_document_reports_database_error_when_processing_cannot_start(
    tmp_path: Path,
    db_session: AsyncMock,
) -> None:
    document = build_document(tmp_path)
    db_session.commit.side_effect = SQLAlchemyError("Database unavailable")

    with pytest.raises(
        DocumentProcessingError,
        match="Doküman durumu güncellenemedi",
    ):
        await process_document(
            document=document,
            session=db_session,
        )

    assert document.status == DocumentStatus.PROCESSING
    db_session.commit.assert_awaited_once()
    db_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_document_reports_database_error_when_failure_cannot_be_saved(
    tmp_path: Path,
    db_session: AsyncMock,
) -> None:
    document = build_document(tmp_path)
    db_session.commit.side_effect = [
        None,
        SQLAlchemyError("Database unavailable"),
    ]

    with (
        patch(
            "app.services.document_processing_service.parse_pdf",
            side_effect=PdfParsingError("PDF dosyası okunamadı."),
        ),
        pytest.raises(
            DocumentProcessingError,
            match="Doküman işleme hatası kaydedilemedi",
        ),
    ):
        await process_document(
            document=document,
            session=db_session,
        )

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "PDF dosyası okunamadı."
    assert db_session.commit.await_count == 2
    assert db_session.rollback.await_count == 2
