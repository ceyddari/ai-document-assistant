from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import Conversation, ConversationDocument, Message
from app.services import (
    ConversationNotFoundError,
    DocumentNotFoundError,
    PersistedExchange,
    RagAnswer,
    persist_rag_exchange,
    set_conversation_documents,
)
from app.services.conversation_service import organization_document_ids


def scalars_result(values: list) -> MagicMock:
    result = MagicMock()
    result.all.return_value = values
    return result


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_organization_document_ids_keeps_order_drops_foreign_and_duplicates(
    session: AsyncMock,
) -> None:
    first, second, foreign = uuid4(), uuid4(), uuid4()
    session.scalars.return_value = scalars_result([second, first])

    result = await organization_document_ids(
        organization_id=uuid4(), document_ids=[first, foreign, second, first], session=session
    )

    assert result == [first, second]
    assert "documents.organization_id" in str(session.scalars.await_args.args[0])


@pytest.mark.asyncio
async def test_organization_document_ids_skips_query_for_empty_input(session: AsyncMock) -> None:
    assert (
        await organization_document_ids(organization_id=uuid4(), document_ids=[], session=session)
        == []
    )
    session.scalars.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_conversation_documents_refuses_foreign_documents(session: AsyncMock) -> None:
    own, foreign = uuid4(), uuid4()
    session.scalar.return_value = MagicMock(spec=Conversation)
    session.scalars.return_value = scalars_result([own])

    with pytest.raises(DocumentNotFoundError):
        await set_conversation_documents(
            organization_id=uuid4(),
            conversation_id=uuid4(),
            document_ids=[own, foreign],
            session=session,
        )

    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_conversation_documents_replaces_scope_in_given_order(session: AsyncMock) -> None:
    first, second = uuid4(), uuid4()
    conversation_id = uuid4()
    session.scalar.return_value = MagicMock(spec=Conversation)
    session.scalars.return_value = scalars_result([first, second])

    result = await set_conversation_documents(
        organization_id=uuid4(),
        conversation_id=conversation_id,
        document_ids=[second, first],
        session=session,
    )

    assert result == [second, first]
    assert "DELETE FROM conversation_documents" in str(session.execute.await_args.args[0])
    rows = list(session.add_all.call_args.args[0])
    assert [(row.document_id, row.position) for row in rows] == [(second, 0), (first, 1)]
    assert all(row.conversation_id == conversation_id for row in rows)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_conversation_documents_empty_list_lifts_scope(session: AsyncMock) -> None:
    session.scalar.return_value = MagicMock(spec=Conversation)

    assert (
        await set_conversation_documents(
            organization_id=uuid4(), conversation_id=uuid4(), document_ids=[], session=session
        )
        == []
    )

    session.execute.assert_awaited_once()
    assert list(session.add_all.call_args.args[0]) == []
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_conversation_documents_enforces_organization(session: AsyncMock) -> None:
    session.scalar.return_value = None

    with pytest.raises(ConversationNotFoundError):
        await set_conversation_documents(
            organization_id=uuid4(),
            conversation_id=uuid4(),
            document_ids=[uuid4()],
            session=session,
        )

    session.commit.assert_not_awaited()


def prepare_persist(session: AsyncMock) -> None:
    async def assign_ids() -> None:
        if session.add.call_args:
            session.add.call_args.args[0].id = session.add.call_args.args[0].id or uuid4()
        for call in session.add_all.call_args_list:
            for model in call.args[0]:
                if hasattr(model, "id") and not isinstance(model, ConversationDocument):
                    model.id = model.id or uuid4()

    session.flush.side_effect = assign_ids
    session.scalar.return_value = None


@pytest.mark.asyncio
async def test_persist_saves_scope_for_new_conversation(session: AsyncMock) -> None:
    kept, deleted_meanwhile = uuid4(), uuid4()
    prepare_persist(session)
    session.scalars.return_value = scalars_result([kept])

    result = await persist_rag_exchange(
        organization_id=uuid4(),
        conversation_id=None,
        question="Soru",
        answer="Cevap",
        sources=[],
        session=session,
        document_ids=[kept, deleted_meanwhile],
    )

    scope_rows = [
        model
        for call in session.add_all.call_args_list
        for model in call.args[0]
        if isinstance(model, ConversationDocument)
    ]
    assert [(row.document_id, row.position) for row in scope_rows] == [(kept, 0)]
    assert scope_rows[0].conversation_id == result.conversation.id


@pytest.mark.asyncio
async def test_persist_does_not_touch_scope_of_existing_conversation(session: AsyncMock) -> None:
    conversation = Conversation(id=uuid4(), organization_id=uuid4(), title="Var olan")
    session.scalar.side_effect = [conversation, 2]

    async def assign_ids() -> None:
        for call in session.add_all.call_args_list:
            for model in call.args[0]:
                model.id = uuid4()

    session.flush.side_effect = assign_ids

    await persist_rag_exchange(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        question="Soru",
        answer="Cevap",
        sources=[],
        session=session,
        document_ids=[uuid4()],
    )

    session.scalars.assert_not_awaited()
    assert not any(
        isinstance(model, ConversationDocument)
        for call in session.add_all.call_args_list
        for model in call.args[0]
    )


# --- routes


@pytest.fixture
def client(session: AsyncMock) -> Iterator[TestClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_settings] = lambda: Settings(
        postgres_db="d",
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=1,
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_put_documents_returns_saved_scope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    document_ids = [uuid4(), uuid4()]
    set_mock = AsyncMock(return_value=document_ids)
    monkeypatch.setattr("app.api.routes.conversations.set_conversation_documents", set_mock)

    response = client.put(
        f"/organizations/{uuid4()}/conversations/{uuid4()}/documents",
        json={"document_ids": [str(item) for item in document_ids]},
    )

    assert response.status_code == 200
    assert response.json() == [str(item) for item in document_ids]
    assert set_mock.await_args.kwargs["document_ids"] == document_ids


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (DocumentNotFoundError("Doküman bulunamadı."), 404),
        (ConversationNotFoundError("Konuşma bulunamadı."), 404),
        (SQLAlchemyError("down"), 503),
    ],
)
def test_put_documents_maps_errors(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    monkeypatch.setattr(
        "app.api.routes.conversations.set_conversation_documents", AsyncMock(side_effect=error)
    )

    response = client.put(
        f"/organizations/{uuid4()}/conversations/{uuid4()}/documents", json={"document_ids": []}
    )

    assert response.status_code == expected_status


def test_put_documents_rejects_more_than_100(client: TestClient) -> None:
    response = client.put(
        f"/organizations/{uuid4()}/conversations/{uuid4()}/documents",
        json={"document_ids": [str(uuid4()) for _ in range(101)]},
    )

    assert response.status_code == 422


def test_conversation_list_includes_scope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    timestamp = datetime.now(UTC)
    scoped = Conversation(
        id=uuid4(), organization_id=uuid4(), title="A", created_at=timestamp, updated_at=timestamp
    )
    open_ = Conversation(
        id=uuid4(), organization_id=uuid4(), title="B", created_at=timestamp, updated_at=timestamp
    )
    document_id = uuid4()
    monkeypatch.setattr(
        "app.api.routes.conversations.list_conversations",
        AsyncMock(return_value=([scoped, open_], 2)),
    )
    monkeypatch.setattr(
        "app.api.routes.conversations.conversation_document_ids",
        AsyncMock(return_value={scoped.id: [document_id]}),
    )

    items = client.get(f"/organizations/{uuid4()}/conversations").json()["items"]

    assert items[0]["document_ids"] == [str(document_id)]
    assert items[1]["document_ids"] == []


@pytest.fixture
def ask_mocks(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    exchange = PersistedExchange(
        conversation=MagicMock(spec=Conversation, id=uuid4()),
        user_message=MagicMock(spec=Message, id=uuid4()),
        assistant_message=MagicMock(spec=Message, id=uuid4()),
    )
    mocks = {
        "answer": AsyncMock(return_value=RagAnswer(answer="Cevap", sources=[])),
        "persist": AsyncMock(return_value=exchange),
        "history": AsyncMock(return_value=[]),
    }
    monkeypatch.setattr("app.api.routes.ask.answer_question", mocks["answer"])
    monkeypatch.setattr("app.api.routes.ask.persist_rag_exchange", mocks["persist"])
    monkeypatch.setattr("app.api.routes.ask.get_recent_messages", mocks["history"])
    monkeypatch.setattr("app.api.routes.ask.EmbeddingService", MagicMock())
    monkeypatch.setattr("app.api.routes.ask.LlmService", MagicMock())
    return mocks


def test_ask_uses_saved_scope_over_request_documents(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, ask_mocks: dict[str, AsyncMock]
) -> None:
    conversation_id, saved = uuid4(), uuid4()
    monkeypatch.setattr(
        "app.api.routes.ask.conversation_document_ids",
        AsyncMock(return_value={conversation_id: [saved]}),
    )

    client.post(
        f"/organizations/{uuid4()}/ask",
        json={
            "question": "Soru",
            "conversation_id": str(conversation_id),
            "document_ids": [str(uuid4())],
        },
    )

    assert ask_mocks["answer"].await_args.kwargs["document_ids"] == [saved]


def test_ask_without_saved_scope_uses_request_documents(
    client: TestClient, ask_mocks: dict[str, AsyncMock]
) -> None:
    requested = uuid4()

    client.post(
        f"/organizations/{uuid4()}/ask",
        json={
            "question": "Soru",
            "conversation_id": str(uuid4()),
            "document_ids": [str(requested)],
        },
    )

    assert ask_mocks["answer"].await_args.kwargs["document_ids"] == [requested]


def test_new_conversation_passes_request_scope_to_answer_and_save(
    client: TestClient, ask_mocks: dict[str, AsyncMock]
) -> None:
    requested = uuid4()

    client.post(
        f"/organizations/{uuid4()}/ask", json={"question": "Soru", "document_ids": [str(requested)]}
    )

    assert ask_mocks["answer"].await_args.kwargs["document_ids"] == [requested]
    assert ask_mocks["persist"].await_args.kwargs["document_ids"] == [requested]
    ask_mocks["history"].assert_not_awaited()


def test_empty_document_list_means_no_scope(
    client: TestClient, ask_mocks: dict[str, AsyncMock]
) -> None:
    client.post(f"/organizations/{uuid4()}/ask", json={"question": "Soru", "document_ids": []})

    assert ask_mocks["answer"].await_args.kwargs["document_ids"] is None
