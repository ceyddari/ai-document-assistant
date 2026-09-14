from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document
from app.services import DocumentProcessingError
from app.tasks.document_tasks import process_document_in_background


def create_session_factory(
    session: AsyncMock,
) -> MagicMock:
    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=session)
    context_manager.__aexit__ = AsyncMock(return_value=None)

    return MagicMock(return_value=context_manager)


@pytest.mark.asyncio
async def test_process_document_in_background_processes_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()
    document = MagicMock(spec=Document)
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = document

    session_factory = create_session_factory(session)
    settings = MagicMock()
    embedding_service = MagicMock()
    process_document_mock = AsyncMock()

    monkeypatch.setattr(
        "app.tasks.document_tasks.get_session_factory",
        lambda: session_factory,
    )
    monkeypatch.setattr(
        "app.tasks.document_tasks.get_settings",
        lambda: settings,
    )
    embedding_service_class_mock = MagicMock(
        return_value=embedding_service,
    )
    monkeypatch.setattr(
        "app.tasks.document_tasks.EmbeddingService",
        embedding_service_class_mock,
    )
    monkeypatch.setattr(
        "app.tasks.document_tasks.process_document",
        process_document_mock,
    )

    await process_document_in_background(document_id)

    session.get.assert_awaited_once_with(Document, document_id)
    embedding_service_class_mock.assert_called_once_with(
        settings=settings,
    )
    process_document_mock.assert_awaited_once_with(
        document=document,
        session=session,
        embedding_service=embedding_service,
    )


@pytest.mark.asyncio
async def test_process_document_in_background_stops_when_document_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = None

    session_factory = create_session_factory(session)
    process_document_mock = AsyncMock()

    monkeypatch.setattr(
        "app.tasks.document_tasks.get_session_factory",
        lambda: session_factory,
    )
    monkeypatch.setattr(
        "app.tasks.document_tasks.process_document",
        process_document_mock,
    )

    await process_document_in_background(document_id)

    session.get.assert_awaited_once_with(Document, document_id)
    process_document_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_document_in_background_handles_processing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()
    document = MagicMock(spec=Document)
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = document

    session_factory = create_session_factory(session)
    embedding_service = MagicMock()
    process_document_mock = AsyncMock(
        side_effect=DocumentProcessingError("Doküman işlenemedi."),
    )

    monkeypatch.setattr(
        "app.tasks.document_tasks.get_session_factory",
        lambda: session_factory,
    )
    monkeypatch.setattr(
        "app.tasks.document_tasks.get_settings",
        MagicMock(),
    )
    monkeypatch.setattr(
        "app.tasks.document_tasks.EmbeddingService",
        MagicMock(return_value=embedding_service),
    )
    monkeypatch.setattr(
        "app.tasks.document_tasks.process_document",
        process_document_mock,
    )

    await process_document_in_background(document_id)

    process_document_mock.assert_awaited_once()
