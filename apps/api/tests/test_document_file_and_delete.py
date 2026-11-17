from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import Document, DocumentStatus
from app.services import (
    DocumentBusyError,
    DocumentNotFoundError,
    delete_document,
    resolve_document_file,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        postgres_db="test_database",
        postgres_user="test_user",
        postgres_password="test_password",
        postgres_host="localhost",
        postgres_port=5432,
        storage_directory=tmp_path / "documents",
    )


@pytest.fixture
def db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def client(db_session: AsyncMock, settings: Settings) -> Iterator[TestClient]:
    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def build_document(storage_path: Path, status: DocumentStatus = DocumentStatus.READY) -> Document:
    timestamp = datetime.now(UTC)
    return Document(
        id=uuid4(),
        organization_id=uuid4(),
        original_filename="Güncel rapor.pdf",
        stored_filename=storage_path.name,
        storage_path=storage_path.as_posix(),
        content_type="application/pdf",
        size_bytes=10,
        status=status,
        created_at=timestamp,
        updated_at=timestamp,
    )


def stored_pdf(settings: Settings) -> Path:
    settings.storage_directory.mkdir(parents=True, exist_ok=True)
    path = settings.storage_directory / f"{uuid4()}.pdf"
    path.write_bytes(b"%PDF-1.7 test")
    return path


def test_resolve_document_file_returns_stored_file(settings: Settings) -> None:
    path = stored_pdf(settings)

    assert resolve_document_file(document=build_document(path), settings=settings) == path.resolve()


def test_resolve_document_file_rejects_paths_outside_storage(
    settings: Settings, tmp_path: Path
) -> None:
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(b"%PDF-")
    stored_pdf(settings)  # storage exists, but the row points elsewhere

    for path in (outside, settings.storage_directory / ".." / "secret.pdf"):
        with pytest.raises(DocumentNotFoundError):
            resolve_document_file(document=build_document(path), settings=settings)


def test_resolve_document_file_rejects_missing_file(settings: Settings) -> None:
    settings.storage_directory.mkdir(parents=True)

    with pytest.raises(DocumentNotFoundError):
        resolve_document_file(
            document=build_document(settings.storage_directory / "missing.pdf"),
            settings=settings,
        )


def test_get_document_file_serves_pdf_inline(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = build_document(stored_pdf(settings))
    monkeypatch.setattr(
        "app.api.routes.documents.get_document_by_id", AsyncMock(return_value=document)
    )

    response = client.get(f"/organizations/{document.organization_id}/documents/{document.id}/file")

    assert response.status_code == 200
    assert response.content == b"%PDF-1.7 test"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["cache-control"] == "private, no-store"


def test_get_document_file_returns_404_for_unknown_document(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.documents.get_document_by_id",
        AsyncMock(side_effect=DocumentNotFoundError("Doküman bulunamadı.")),
    )

    response = client.get(f"/organizations/{uuid4()}/documents/{uuid4()}/file")

    assert response.status_code == 404


def test_delete_document_route_removes_row_then_file(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = stored_pdf(settings)
    delete_mock = AsyncMock(return_value=path)
    monkeypatch.setattr("app.api.routes.documents.delete_document", delete_mock)

    response = client.delete(f"/organizations/{uuid4()}/documents/{uuid4()}")

    assert response.status_code == 204
    assert not path.exists()


def test_delete_document_route_never_unlinks_outside_storage(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "keep.pdf"
    outside.write_bytes(b"%PDF-")
    monkeypatch.setattr("app.api.routes.documents.delete_document", AsyncMock(return_value=outside))

    response = client.delete(f"/organizations/{uuid4()}/documents/{uuid4()}")

    assert response.status_code == 204
    assert outside.exists()


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (DocumentNotFoundError("Doküman bulunamadı."), 404),
        (DocumentBusyError("İşlenmekte olan doküman silinemez."), 409),
        (SQLAlchemyError("down"), 503),
    ],
)
def test_delete_document_route_maps_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    monkeypatch.setattr("app.api.routes.documents.delete_document", AsyncMock(side_effect=error))

    response = client.delete(f"/organizations/{uuid4()}/documents/{uuid4()}")

    assert response.status_code == expected_status


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [DocumentStatus.PENDING, DocumentStatus.PROCESSING])
async def test_delete_document_refuses_document_being_processed(
    tmp_path: Path, status: DocumentStatus
) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = build_document(tmp_path / "a.pdf", status)

    with pytest.raises(DocumentBusyError):
        await delete_document(organization_id=uuid4(), document_id=uuid4(), session=session)

    session.delete.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_document_deletes_locked_row_and_returns_path(tmp_path: Path) -> None:
    document = build_document(tmp_path / "a.pdf")
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = document

    path = await delete_document(
        organization_id=document.organization_id, document_id=document.id, session=session
    )

    assert path == tmp_path / "a.pdf"
    session.delete.assert_awaited_once_with(document)
    session.commit.assert_awaited_once()
    assert "FOR UPDATE" in str(session.scalar.await_args.args[0].compile())


@pytest.mark.asyncio
async def test_delete_document_raises_for_unknown_document() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None

    with pytest.raises(DocumentNotFoundError):
        await delete_document(organization_id=uuid4(), document_id=uuid4(), session=session)

    session.delete.assert_not_awaited()
