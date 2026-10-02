from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.main import app
from app.models import Conversation, Message, MessageRole
from app.services import ConversationNotFoundError, OrganizationNotFoundError, RetrievedChunk
from app.services.conversation_service import MessageWithSources


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def service_mocks(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    mocks = {
        "create": AsyncMock(),
        "list": AsyncMock(),
        "get": AsyncMock(),
    }
    monkeypatch.setattr("app.api.routes.conversations.create_conversation", mocks["create"])
    monkeypatch.setattr("app.api.routes.conversations.list_conversations", mocks["list"])
    monkeypatch.setattr("app.api.routes.conversations.get_conversation_with_messages", mocks["get"])
    return mocks


@pytest.fixture
def client(session: AsyncMock) -> Iterator[TestClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def build_conversation(organization_id, *, title="İzin") -> Conversation:
    timestamp = datetime.now(UTC)
    return Conversation(
        id=uuid4(),
        organization_id=organization_id,
        title=title,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_create_conversation_returns_201(
    client: TestClient,
    session: AsyncMock,
    service_mocks: dict[str, AsyncMock],
) -> None:
    organization_id = uuid4()
    conversation = build_conversation(organization_id)
    service_mocks["create"].return_value = conversation

    response = client.post(
        f"/organizations/{organization_id}/conversations",
        json={"title": "  İzin  "},
    )

    assert response.status_code == 201
    assert response.json()["id"] == str(conversation.id)
    service_mocks["create"].assert_awaited_once_with(
        organization_id=organization_id,
        title="İzin",
        session=session,
    )


def test_list_conversations_returns_pagination(
    client: TestClient,
    service_mocks: dict[str, AsyncMock],
) -> None:
    organization_id = uuid4()
    conversation = build_conversation(organization_id)
    service_mocks["list"].return_value = ([conversation], 1)

    response = client.get(f"/organizations/{organization_id}/conversations?limit=10&offset=0")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == str(conversation.id)


def test_get_conversation_returns_messages(
    client: TestClient,
    service_mocks: dict[str, AsyncMock],
) -> None:
    organization_id = uuid4()
    conversation = build_conversation(organization_id)
    message = Message(
        id=uuid4(),
        organization_id=organization_id,
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="Yıllık izin nasıl alınır?",
        created_at=datetime.now(UTC),
    )
    source = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="policy.pdf",
        page_number=1,
        content="İzin talebi sistemden oluşturulur.",
        similarity=0.8,
    )
    service_mocks["get"].return_value = (
        conversation,
        [MessageWithSources(message=message, sources=[source])],
    )

    response = client.get(f"/organizations/{organization_id}/conversations/{conversation.id}")

    assert response.status_code == 200
    assert response.json()["messages"][0]["role"] == "user"
    assert response.json()["messages"][0]["content"] == message.content
    assert response.json()["messages"][0]["sources"][0]["chunk_id"] == str(source.chunk_id)


@pytest.mark.parametrize(
    ("method", "service_key", "service_error"),
    [
        ("post", "create", OrganizationNotFoundError("Organizasyon bulunamadı.")),
        ("get", "get", ConversationNotFoundError("Konuşma bulunamadı.")),
    ],
)
def test_conversation_routes_return_404(
    client: TestClient,
    service_mocks: dict[str, AsyncMock],
    method: str,
    service_key: str,
    service_error: Exception,
) -> None:
    organization_id = uuid4()
    conversation_id = uuid4()
    service_mocks[service_key].side_effect = service_error
    url = f"/organizations/{organization_id}/conversations"

    if method == "post":
        response = client.post(url, json={})
    else:
        response = client.get(f"{url}/{conversation_id}")

    assert response.status_code == 404
