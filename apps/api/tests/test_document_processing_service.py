from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    EMBEDDING_DIMENSIONS,
    Document,
    DocumentStatus,
)
from app.services import (
    DocumentProcessingError,
    EmbeddingService,
    EmbeddingServiceError,
    ParsedPage,
    PdfParsingError,
    TextChunk,
    process_document,
)


@pytest.fixture
def db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def embedding_service() -> AsyncMock:
    return AsyncMock(spec=EmbeddingService)


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
async def test_process_document_creates_chunks_and_marks_document_as_ready(
    tmp_path: Path,
    db_session: AsyncMock,
    embedding_service: AsyncMock,
) -> None:
    document = build_document(tmp_path)

    parsed_pages = [
        ParsedPage(
            page_number=1,
            text="First page content",
        ),
        ParsedPage(
            page_number=2,
            text="Second page content",
        ),
    ]

    text_chunks = [
        TextChunk(
            page_number=1,
            chunk_index=0,
            content="First page content",
        ),
        TextChunk(
            page_number=2,
            chunk_index=1,
            content="Second page content",
        ),
    ]

    embeddings = [
        [0.1] * EMBEDDING_DIMENSIONS,
        [0.2] * EMBEDDING_DIMENSIONS,
    ]

    embedding_service.embed_documents.return_value = embeddings

    embedding_service.embed_documents.return_value = embeddings

    with (
        patch(
            "app.services.document_processing_service.parse_pdf",
            return_value=parsed_pages,
        ) as parse_pdf_mock,
        patch(
            "app.services.document_processing_service.chunk_pages",
            return_value=text_chunks,
        ) as chunk_pages_mock,
    ):
        document_chunks = await process_document(
            document=document,
            session=db_session,
            embedding_service=embedding_service,
        )

    assert document.status == DocumentStatus.READY
    assert document.error_message is None
    assert len(document_chunks) == 2

    assert document_chunks[0].organization_id == document.organization_id
    assert document_chunks[0].document_id == document.id
    assert document_chunks[0].page_number == 1
    assert document_chunks[0].chunk_index == 0
    assert document_chunks[0].content == "First page content"
    assert document_chunks[0].embedding == embeddings[0]

    assert document_chunks[1].page_number == 2
    assert document_chunks[1].chunk_index == 1
    assert document_chunks[1].content == "Second page content"
    assert document_chunks[1].embedding == embeddings[1]

    parse_pdf_mock.assert_called_once_with(
        Path(document.storage_path),
    )
    chunk_pages_mock.assert_called_once_with(parsed_pages)

    embedding_service.embed_documents.assert_awaited_once_with(
        [
            "First page content",
            "Second page content",
        ]
    )

    db_session.add_all.assert_called_once_with(document_chunks)
    assert db_session.commit.await_count == 2
    db_session.rollback.assert_not_awaited()
    db_session.refresh.assert_awaited_once_with(document)


@pytest.mark.asyncio
async def test_process_document_marks_document_as_failed_when_pdf_cannot_be_parsed(
    tmp_path: Path,
    db_session: AsyncMock,
    embedding_service: AsyncMock,
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
            embedding_service=embedding_service,
        )

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "PDF dosyası okunamadı."
    assert db_session.commit.await_count == 2
    db_session.rollback.assert_awaited_once()
    db_session.add_all.assert_not_called()
    embedding_service.embed_documents.assert_not_awaited()
    db_session.refresh.assert_awaited_once_with(document)


@pytest.mark.asyncio
async def test_process_document_rejects_document_without_extractable_text(
    tmp_path: Path,
    db_session: AsyncMock,
    embedding_service: AsyncMock,
) -> None:
    document = build_document(tmp_path)

    with (
        patch(
            "app.services.document_processing_service.parse_pdf",
            return_value=[
                ParsedPage(
                    page_number=1,
                    text="",
                )
            ],
        ),
        patch(
            "app.services.document_processing_service.chunk_pages",
            return_value=[],
        ),
        pytest.raises(
            DocumentProcessingError,
            match="Doküman işlenemedi",
        ),
    ):
        await process_document(
            document=document,
            session=db_session,
            embedding_service=embedding_service,
        )

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "Dokümanda işlenebilir metin bulunamadı."

    db_session.add_all.assert_not_called()
    embedding_service.embed_documents.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_document_marks_document_as_failed_when_embedding_fails(
    tmp_path: Path,
    db_session: AsyncMock,
    embedding_service: AsyncMock,
) -> None:
    document = build_document(tmp_path)

    parsed_pages = [
        ParsedPage(
            page_number=1,
            text="Yıllık izin prosedürü.",
        )
    ]
    text_chunks = [
        TextChunk(
            page_number=1,
            chunk_index=0,
            content="Yıllık izin prosedürü.",
        )
    ]

    embedding_service.embed_documents.side_effect = EmbeddingServiceError(
        "Doküman embedding'leri üretilemedi."
    )

    with (
        patch(
            "app.services.document_processing_service.parse_pdf",
            return_value=parsed_pages,
        ),
        patch(
            "app.services.document_processing_service.chunk_pages",
            return_value=text_chunks,
        ),
        pytest.raises(
            DocumentProcessingError,
            match="Doküman işlenemedi",
        ),
    ):
        await process_document(
            document=document,
            session=db_session,
            embedding_service=embedding_service,
        )

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "Doküman embedding'leri üretilemedi."

    db_session.add_all.assert_not_called()


@pytest.mark.asyncio
async def test_process_document_does_not_leave_unexpected_errors_processing(
    tmp_path: Path,
    db_session: AsyncMock,
    embedding_service: AsyncMock,
) -> None:
    document = build_document(tmp_path)

    with (
        patch(
            "app.services.document_processing_service.parse_pdf",
            side_effect=RuntimeError("unexpected parser failure"),
        ),
        pytest.raises(DocumentProcessingError, match="Doküman işlenemedi"),
    ):
        await process_document(
            document=document,
            session=db_session,
            embedding_service=embedding_service,
        )

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "Doküman işlenirken beklenmeyen bir hata oluştu."
    assert db_session.commit.await_count == 2
    db_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_document_reports_database_error_when_processing_cannot_start(
    tmp_path: Path,
    db_session: AsyncMock,
    embedding_service: AsyncMock,
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
            embedding_service=embedding_service,
        )

    assert document.status == DocumentStatus.PROCESSING
    db_session.commit.assert_awaited_once()
    db_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_document_reports_database_error_when_failure_cannot_be_saved(
    tmp_path: Path,
    db_session: AsyncMock,
    embedding_service: AsyncMock,
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
            embedding_service=embedding_service,
        )

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "PDF dosyası okunamadı."
    assert db_session.commit.await_count == 2
    assert db_session.rollback.await_count == 2
