from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.main import app
from app.models import Conversation, Message, MessageRole
from app.services import (
    ConversationNotFoundError,
    MessageNotFoundError,
    delete_conversation,
    rename_conversation,
    set_message_feedback,
)


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
    app.dependency_overrides.clear()


def build_conversation(title: str = "İzin") -> Conversation:
    timestamp = datetime.now(UTC)
    return Conversation(
        id=uuid4(),
        organization_id=uuid4(),
        title=title,
        created_at=timestamp,
        updated_at=timestamp,
    )


def build_assistant_message(feedback: int | None) -> Message:
    return Message(
        id=uuid4(),
        organization_id=uuid4(),
        conversation_id=uuid4(),
        role=MessageRole.ASSISTANT,
        content="Cevap",
        sequence=2,
        feedback=feedback,
        created_at=datetime.now(UTC),
    )


def test_rename_conversation_route_trims_title(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = build_conversation("Yeni ad")
    rename_mock = AsyncMock(return_value=conversation)
    monkeypatch.setattr("app.api.routes.conversations.rename_conversation", rename_mock)

    response = client.patch(
        f"/organizations/{conversation.organization_id}/conversations/{conversation.id}",
        json={"title": "  Yeni ad  "},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Yeni ad"
    assert rename_mock.await_args.kwargs["title"] == "Yeni ad"


@pytest.mark.parametrize("title", ["   ", "x" * 256])
def test_rename_conversation_route_rejects_invalid_title(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, title: str
) -> None:
    rename_mock = AsyncMock()
    monkeypatch.setattr("app.api.routes.conversations.rename_conversation", rename_mock)

    response = client.patch(
        f"/organizations/{uuid4()}/conversations/{uuid4()}", json={"title": title}
    )

    assert response.status_code == 422
    rename_mock.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "target", "kwargs"),
    [
        ("patch", "rename_conversation", {"json": {"title": "Ad"}}),
        ("delete", "delete_conversation", {}),
    ],
)
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [(ConversationNotFoundError("Konuşma bulunamadı."), 404), (SQLAlchemyError("down"), 503)],
)
def test_conversation_actions_map_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    target: str,
    kwargs: dict,
    error: Exception,
    expected_status: int,
) -> None:
    monkeypatch.setattr(f"app.api.routes.conversations.{target}", AsyncMock(side_effect=error))

    response = client.request(
        method.upper(), f"/organizations/{uuid4()}/conversations/{uuid4()}", **kwargs
    )

    assert response.status_code == expected_status


def test_delete_conversation_route_returns_204(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.api.routes.conversations.delete_conversation", delete_mock)

    response = client.delete(f"/organizations/{uuid4()}/conversations/{uuid4()}")

    assert response.status_code == 204
    delete_mock.assert_awaited_once()


@pytest.mark.parametrize("value", [1, -1, None])
def test_feedback_route_accepts_votes_and_clearing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, value: int | None
) -> None:
    message = build_assistant_message(value)
    feedback_mock = AsyncMock(return_value=message)
    monkeypatch.setattr("app.api.routes.conversations.set_message_feedback", feedback_mock)

    response = client.put(
        f"/organizations/{uuid4()}/conversations/{message.conversation_id}"
        f"/messages/{message.id}/feedback",
        json={"value": value},
    )

    assert response.status_code == 200
    assert response.json()["feedback"] == value
    assert feedback_mock.await_args.kwargs["value"] == value


@pytest.mark.parametrize("payload", [{"value": 2}, {"value": 0}, {}])
def test_feedback_route_rejects_other_values(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    feedback_mock = AsyncMock()
    monkeypatch.setattr("app.api.routes.conversations.set_message_feedback", feedback_mock)

    response = client.put(
        f"/organizations/{uuid4()}/conversations/{uuid4()}/messages/{uuid4()}/feedback",
        json=payload,
    )

    assert response.status_code == 422
    feedback_mock.assert_not_awaited()


def test_feedback_route_returns_404_for_unknown_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.routes.conversations.set_message_feedback",
        AsyncMock(side_effect=MessageNotFoundError("Mesaj bulunamadı.")),
    )

    response = client.put(
        f"/organizations/{uuid4()}/conversations/{uuid4()}/messages/{uuid4()}/feedback",
        json={"value": 1},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_set_message_feedback_only_targets_assistant_messages(session: AsyncMock) -> None:
    session.scalar.return_value = None

    with pytest.raises(MessageNotFoundError):
        await set_message_feedback(
            organization_id=uuid4(),
            conversation_id=uuid4(),
            message_id=uuid4(),
            value=1,
            session=session,
        )

    where_sql = str(session.scalar.await_args.args[0])
    assert "messages.role" in where_sql
    assert "messages.organization_id" in where_sql
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_message_feedback_saves_vote(session: AsyncMock) -> None:
    message = build_assistant_message(None)
    session.scalar.return_value = message

    await set_message_feedback(
        organization_id=message.organization_id,
        conversation_id=message.conversation_id,
        message_id=message.id,
        value=-1,
        session=session,
    )

    assert message.feedback == -1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_rename_and_delete_enforce_organization_scope(session: AsyncMock) -> None:
    session.scalar.return_value = None

    with pytest.raises(ConversationNotFoundError):
        await rename_conversation(
            organization_id=uuid4(), conversation_id=uuid4(), title="Ad", session=session
        )
    with pytest.raises(ConversationNotFoundError):
        await delete_conversation(organization_id=uuid4(), conversation_id=uuid4(), session=session)

    session.delete.assert_not_awaited()
    session.commit.assert_not_awaited()
