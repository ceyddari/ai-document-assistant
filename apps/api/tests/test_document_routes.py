from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import Document, DocumentStatus
from app.services import (
    DocumentNotFoundError,
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
def process_document_in_background_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncMock:
    mock = AsyncMock()

    monkeypatch.setattr(
        "app.api.routes.documents.process_document_in_background",
        mock,
    )

    return mock


@pytest.fixture
def list_documents_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()

    monkeypatch.setattr(
        "app.api.routes.documents.list_documents",
        mock,
    )

    return mock


@pytest.fixture
def get_document_by_id_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncMock:
    mock = AsyncMock()

    monkeypatch.setattr(
        "app.api.routes.documents.get_document_by_id",
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


def build_document(
    *,
    organization_id: UUID,
    filename: str,
) -> Document:
    document_id = uuid4()
    timestamp = datetime.now(UTC)

    return Document(
        id=document_id,
        organization_id=organization_id,
        original_filename=filename,
        stored_filename=f"{document_id}.pdf",
        storage_path=f"storage/documents/{document_id}.pdf",
        content_type="application/pdf",
        size_bytes=100,
        status=DocumentStatus.PENDING,
        error_message=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_upload_document_returns_created_document(
    client: TestClient,
    db_session: AsyncMock,
    settings: Settings,
    create_document_mock: AsyncMock,
    process_document_in_background_mock: AsyncMock,
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

    process_document_in_background_mock.assert_awaited_once_with(
        document_id,
    )


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


def test_get_documents_returns_paginated_documents(
    client: TestClient,
    db_session: AsyncMock,
    list_documents_mock: AsyncMock,
) -> None:
    organization_id = uuid4()
    documents = [
        build_document(
            organization_id=organization_id,
            filename="policy.pdf",
        ),
        build_document(
            organization_id=organization_id,
            filename="handbook.pdf",
        ),
    ]
    list_documents_mock.return_value = (documents, 2)

    response = client.get(
        f"/organizations/{organization_id}/documents",
        params={
            "limit": 10,
            "offset": 5,
        },
    )

    assert response.status_code == 200

    response_body = response.json()

    assert response_body["total"] == 2
    assert response_body["limit"] == 10
    assert response_body["offset"] == 5
    assert len(response_body["items"]) == 2
    assert response_body["items"][0]["original_filename"] == "policy.pdf"
    assert response_body["items"][1]["original_filename"] == "handbook.pdf"

    list_documents_mock.assert_awaited_once_with(
        organization_id=organization_id,
        session=db_session,
        limit=10,
        offset=5,
    )


@pytest.mark.parametrize(
    ("service_error", "expected_status", "expected_detail"),
    [
        (
            OrganizationNotFoundError("Organizasyon bulunamadı."),
            404,
            "Organizasyon bulunamadı.",
        ),
        (
            SQLAlchemyError("Database error"),
            503,
            "Dokümanlar şu anda getirilemiyor.",
        ),
    ],
)
def test_get_documents_maps_service_errors_to_http_responses(
    client: TestClient,
    list_documents_mock: AsyncMock,
    service_error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    organization_id = uuid4()
    list_documents_mock.side_effect = service_error

    response = client.get(
        f"/organizations/{organization_id}/documents",
    )

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": expected_detail,
    }


@pytest.mark.parametrize(
    "query_parameters",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ],
)
def test_get_documents_rejects_invalid_pagination(
    client: TestClient,
    list_documents_mock: AsyncMock,
    query_parameters: dict[str, int],
) -> None:
    organization_id = uuid4()

    response = client.get(
        f"/organizations/{organization_id}/documents",
        params=query_parameters,
    )

    assert response.status_code == 422
    list_documents_mock.assert_not_awaited()


def test_get_document_returns_document(
    client: TestClient,
    db_session: AsyncMock,
    get_document_by_id_mock: AsyncMock,
) -> None:
    organization_id = uuid4()
    document = build_document(
        organization_id=organization_id,
        filename="policy.pdf",
    )
    get_document_by_id_mock.return_value = document

    response = client.get(
        f"/organizations/{organization_id}/documents/{document.id}",
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(document.id)
    assert response.json()["organization_id"] == str(organization_id)
    assert response.json()["original_filename"] == "policy.pdf"

    get_document_by_id_mock.assert_awaited_once_with(
        organization_id=organization_id,
        document_id=document.id,
        session=db_session,
    )


@pytest.mark.parametrize(
    ("service_error", "expected_status", "expected_detail"),
    [
        (
            DocumentNotFoundError("Doküman bulunamadı."),
            404,
            "Doküman bulunamadı.",
        ),
        (
            SQLAlchemyError("Database error"),
            503,
            "Doküman şu anda getirilemiyor.",
        ),
    ],
)
def test_get_document_maps_service_errors_to_http_responses(
    client: TestClient,
    get_document_by_id_mock: AsyncMock,
    service_error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    organization_id = uuid4()
    document_id = uuid4()
    get_document_by_id_mock.side_effect = service_error

    response = client.get(
        f"/organizations/{organization_id}/documents/{document_id}",
    )

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": expected_detail,
    }
