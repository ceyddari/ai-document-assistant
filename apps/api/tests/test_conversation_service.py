from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message, MessageRole, Organization
from app.services import (
    ConversationNotFoundError,
    OrganizationNotFoundError,
    create_conversation,
    get_conversation_with_messages,
    list_conversations,
)


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_create_conversation_persists_for_organization(session: AsyncMock) -> None:
    organization_id = uuid4()
    session.get.return_value = MagicMock(spec=Organization)

    conversation = await create_conversation(
        organization_id=organization_id,
        title="İzin prosedürü",
        session=session,
    )

    assert conversation.organization_id == organization_id
    assert conversation.title == "İzin prosedürü"
    session.add.assert_called_once_with(conversation)
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(conversation)


@pytest.mark.asyncio
async def test_create_conversation_rejects_unknown_organization(session: AsyncMock) -> None:
    session.get.return_value = None

    with pytest.raises(OrganizationNotFoundError, match="Organizasyon bulunamadı"):
        await create_conversation(
            organization_id=uuid4(),
            title=None,
            session=session,
        )

    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_conversation_rolls_back_database_error(session: AsyncMock) -> None:
    session.get.return_value = MagicMock(spec=Organization)
    session.commit.side_effect = SQLAlchemyError("Database unavailable")

    with pytest.raises(SQLAlchemyError):
        await create_conversation(
            organization_id=uuid4(),
            title="İzin",
            session=session,
        )

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_conversations_returns_page_and_total(session: AsyncMock) -> None:
    organization_id = uuid4()
    conversations = [
        Conversation(id=uuid4(), organization_id=organization_id, title="Bir"),
        Conversation(id=uuid4(), organization_id=organization_id, title="İki"),
    ]
    scalar_result = MagicMock()
    scalar_result.all.return_value = conversations
    session.get.return_value = MagicMock(spec=Organization)
    session.scalars.return_value = scalar_result
    session.scalar.return_value = 2

    items, total = await list_conversations(
        organization_id=organization_id,
        session=session,
        limit=20,
        offset=0,
    )

    assert items == conversations
    assert total == 2


@pytest.mark.asyncio
async def test_get_conversation_returns_chronological_messages(session: AsyncMock) -> None:
    organization_id = uuid4()
    conversation_id = uuid4()
    timestamp = datetime.now(UTC)
    conversation = Conversation(
        id=conversation_id,
        organization_id=organization_id,
        title="İzin",
    )
    messages = [
        Message(
            id=uuid4(),
            organization_id=organization_id,
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content="Soru",
            created_at=timestamp,
        )
    ]
    scalar_result = MagicMock()
    scalar_result.all.return_value = messages
    session.scalar.return_value = conversation
    session.scalars.return_value = scalar_result

    result_conversation, result_messages = await get_conversation_with_messages(
        organization_id=organization_id,
        conversation_id=conversation_id,
        session=session,
    )

    assert result_conversation is conversation
    assert result_messages == messages


@pytest.mark.asyncio
async def test_get_conversation_enforces_organization_scope(session: AsyncMock) -> None:
    session.scalar.return_value = None

    with pytest.raises(ConversationNotFoundError, match="Konuşma bulunamadı"):
        await get_conversation_with_messages(
            organization_id=uuid4(),
            conversation_id=uuid4(),
            session=session,
        )

    session.scalars.assert_not_awaited()
