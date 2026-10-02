from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_organization_member
from app.db.session import get_db_session
from app.main import app
from app.models import Organization, User
from app.services.auth_service import CredentialsError, IssuedToken


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def client(session: AsyncMock) -> Iterator[TestClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db_session, None)


def test_login_returns_bearer_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user = User(
        id=uuid4(), email="user@example.com", password_hash="hidden", created_at=datetime.now(UTC)
    )
    token = IssuedToken(
        value="raw-session-token", expires_at=datetime.now(UTC) + timedelta(hours=24)
    )
    authenticate = AsyncMock(return_value=(user, token))
    monkeypatch.setattr("app.api.routes.auth.authenticate_user", authenticate)
    memberships = AsyncMock(return_value=[uuid4()])
    monkeypatch.setattr("app.api.routes.auth.list_user_organization_ids", memberships)

    response = client.post(
        "/auth/login", json={"email": "USER@example.com", "password": "valid-password-123"}
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == token.value
    assert response.json()["token_type"] == "bearer"
    assert response.json()["organization_ids"] == [str(memberships.return_value[0])]
    authenticate.assert_awaited_once()


def test_login_rejects_invalid_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    authenticate = AsyncMock(side_effect=CredentialsError("E-posta veya parola hatalı."))
    monkeypatch.setattr("app.api.routes.auth.authenticate_user", authenticate)

    response = client.post("/auth/login", json={"email": "user@example.com", "password": "wrong"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_requires_authentication(client: TestClient) -> None:
    app.dependency_overrides.pop(get_current_user, None)
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_organization_routes_require_authentication(client: TestClient) -> None:
    app.dependency_overrides.pop(require_organization_member, None)
    response = client.get(f"/organizations/{uuid4()}/documents")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_register_returns_user_organization_and_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = User(
        id=uuid4(), email="owner@example.com", password_hash="hidden", created_at=datetime.now(UTC)
    )
    organization = Organization(id=uuid4(), name="Acme", slug="acme", created_at=datetime.now(UTC))
    token = IssuedToken(value="new-token", expires_at=datetime.now(UTC) + timedelta(hours=24))
    register = AsyncMock(return_value=(user, organization, token))
    monkeypatch.setattr("app.api.routes.auth.register_user_and_organization", register)

    response = client.post(
        "/auth/register",
        json={
            "email": "owner@example.com",
            "password": "strong-password-123",
            "organization_name": "Acme",
            "organization_slug": "acme",
        },
    )

    assert response.status_code == 201
    assert response.json()["organization_id"] == str(organization.id)
    assert response.json()["access_token"] == token.value


def test_register_requires_at_least_six_character_password(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={
            "email": "owner@example.com",
            "password": "12345",
            "organization_name": "Acme",
            "organization_slug": "acme",
        },
    )

    assert response.status_code == 422
