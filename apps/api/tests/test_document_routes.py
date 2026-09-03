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
    DocumentTooLargeError,
    InvalidPdfError,
    OrganizationNotFoundError,
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


@pytest.fixture
def create_document_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()

    monkeypatch.setattr(
        "app.api.routes.documents.create_document",
        mock,
    )

    return mock


@pytest.fixture
def client(
    db_session: AsyncMock,
    settings: Settings,
) -> Iterator[TestClient]:
    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_upload_document_returns_created_document(
    client: TestClient,
    db_session: AsyncMock,
    settings: Settings,
    create_document_mock: AsyncMock,
) -> None:
    organization_id = uuid4()
    document_id = uuid4()
    timestamp = datetime.now(UTC)

    document = Document(
        id=document_id,
        organization_id=organization_id,
        original_filename="policy.pdf",
        stored_filename=f"{document_id}.pdf",
        storage_path=f"storage/documents/{document_id}.pdf",
        content_type="application/pdf",
        size_bytes=24,
        status=DocumentStatus.PENDING,
        error_message=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    create_document_mock.return_value = document

    response = client.post(
        f"/organizations/{organization_id}/documents",
        files={
            "file": (
                "policy.pdf",
                b"%PDF-1.7\nTest PDF content",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(document_id),
        "organization_id": str(organization_id),
        "original_filename": "policy.pdf",
        "content_type": "application/pdf",
        "size_bytes": 24,
        "status": "pending",
        "error_message": None,
        "created_at": timestamp.isoformat().replace("+00:00", "Z"),
        "updated_at": timestamp.isoformat().replace("+00:00", "Z"),
    }

    create_document_mock.assert_awaited_once()

    call_arguments = create_document_mock.await_args.kwargs

    assert call_arguments["organization_id"] == organization_id
    assert call_arguments["session"] is db_session
    assert call_arguments["settings"] is settings
    assert call_arguments["file"].filename == "policy.pdf"


@pytest.mark.parametrize(
    ("service_error", "expected_status", "expected_detail"),
    [
        (
            OrganizationNotFoundError("Organizasyon bulunamadı."),
            404,
            "Organizasyon bulunamadı.",
        ),
        (
            InvalidPdfError("Dosya geçerli bir PDF değil."),
            400,
            "Dosya geçerli bir PDF değil.",
        ),
        (
            DocumentTooLargeError("Dosya en fazla 1 MB olabilir."),
            413,
            "Dosya en fazla 1 MB olabilir.",
        ),
        (
            SQLAlchemyError("Database error"),
            503,
            "Doküman şu anda kaydedilemiyor.",
        ),
    ],
)
def test_upload_document_maps_service_errors_to_http_responses(
    client: TestClient,
    create_document_mock: AsyncMock,
    service_error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    organization_id = uuid4()
    create_document_mock.side_effect = service_error

    response = client.post(
        f"/organizations/{organization_id}/documents",
        files={
            "file": (
                "policy.pdf",
                b"%PDF-1.7\nTest PDF content",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": expected_detail,
    }
