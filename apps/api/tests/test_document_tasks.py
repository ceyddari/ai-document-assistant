import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document
from app.services import DocumentProcessingError
from app.services.llm_service import LlmServiceError
from app.tasks.document_tasks import (
    process_document_in_background,
    summarize_document_in_background,
)


@pytest.fixture(autouse=True)
def summarize(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr("app.tasks.document_tasks.summarize_document_in_background", mock)
    return mock


def create_session_factory(
    session: AsyncMock,
) -> MagicMock:
    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=session)
    context_manager.__aexit__ = AsyncMock(return_value=None)

    return MagicMock(return_value=context_manager)


@pytest.mark.asyncio
async def test_process_document_in_background_processes_document(
    monkeypatch: pytest.MonkeyPatch, summarize: AsyncMock
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
    summarize.assert_awaited_once_with(document_id)


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
    monkeypatch: pytest.MonkeyPatch, summarize: AsyncMock
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
    summarize.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_document_in_background_runs_one_document_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = MagicMock(spec=Document)
    running = 0
    peak = 0

    async def slow_process(**_: object) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1

    # A fresh semaphore binds to this test's event loop.
    monkeypatch.setattr("app.tasks.document_tasks._processing_slot", asyncio.Semaphore(1))
    monkeypatch.setattr(
        "app.tasks.document_tasks.get_session_factory",
        lambda: create_session_factory(session),
    )
    monkeypatch.setattr("app.tasks.document_tasks.get_settings", MagicMock())
    monkeypatch.setattr("app.tasks.document_tasks.EmbeddingService", MagicMock())
    monkeypatch.setattr(
        "app.tasks.document_tasks.process_document", AsyncMock(side_effect=slow_process)
    )

    await asyncio.gather(*(process_document_in_background(uuid4()) for _ in range(3)))

    assert peak == 1
    assert session.get.await_count == 3


@pytest.mark.asyncio
async def test_summary_failure_is_logged_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    # The autouse fixture replaced the module attribute; this test needs the real function.
    session = AsyncMock(spec=AsyncSession)
    monkeypatch.setattr("app.tasks.document_tasks._summary_slot", asyncio.Semaphore(1))
    monkeypatch.setattr(
        "app.tasks.document_tasks.get_session_factory", lambda: create_session_factory(session)
    )
    monkeypatch.setattr("app.tasks.document_tasks.get_settings", MagicMock())
    monkeypatch.setattr("app.tasks.document_tasks.LlmService", MagicMock())
    monkeypatch.setattr(
        "app.tasks.document_tasks.summarize_document",
        AsyncMock(side_effect=LlmServiceError("zaman aşımı")),
    )

    await summarize_document_in_background(uuid4())

    session.rollback.assert_awaited_once()
