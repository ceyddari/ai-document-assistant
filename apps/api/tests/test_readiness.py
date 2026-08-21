from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.main import app


@pytest.fixture
def db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def client(db_session: AsyncMock) -> Iterator[TestClient]:
    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_readiness_returns_ready(
    client: TestClient,
    db_session: AsyncMock,
) -> None:
    response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    db_session.execute.assert_awaited_once()


def test_readiness_returns_503_when_database_is_unavailable(
    client: TestClient,
    db_session: AsyncMock,
) -> None:
    db_session.execute.side_effect = SQLAlchemyError("Database connection failed")

    response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}
