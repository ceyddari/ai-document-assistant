from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, MessageRole, MessageSource
from app.services import (
    ConversationNotFoundError,
    RetrievedChunk,
    persist_rag_exchange,
)


def build_source() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="policy.pdf",
        page_number=1,
        content="İzin talebi sistemden oluşturulur.",
        similarity=0.8,
    )


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_persist_rag_exchange_creates_conversation_messages_and_sources(
    session: AsyncMock,
) -> None:
    organization_id = uuid4()
    source = build_source()
    flush_count = 0

    async def assign_ids() -> None:
        nonlocal flush_count
        flush_count += 1
        if flush_count == 1:
            conversation = session.add.call_args.args[0]
            conversation.id = uuid4()
        else:
            messages = session.add_all.call_args_list[0].args[0]
            for message in messages:
                message.id = uuid4()

    session.flush.side_effect = assign_ids

    result = await persist_rag_exchange(
        organization_id=organization_id,
        conversation_id=None,
        question="Yıllık izin nasıl alınır?",
        answer="Sistemden talep edilir. [Kaynak 1]",
        sources=[source],
        session=session,
    )

    assert result.conversation.title == "Yıllık izin nasıl alınır?"
    assert result.user_message.role == MessageRole.USER
    assert result.assistant_message.role == MessageRole.ASSISTANT
    source_models = session.add_all.call_args_list[1].args[0]
    assert len(source_models) == 1
    assert isinstance(source_models[0], MessageSource)
    assert source_models[0].chunk_id == source.chunk_id
    assert source_models[0].similarity == 0.8
    session.commit.assert_awaited_once()
    assert session.refresh.await_count == 3


@pytest.mark.asyncio
async def test_persist_rag_exchange_appends_to_existing_conversation(
    session: AsyncMock,
) -> None:
    organization_id = uuid4()
    conversation = Conversation(
        id=uuid4(),
        organization_id=organization_id,
        title="İzin",
    )
    session.scalar.return_value = conversation

    async def assign_message_ids() -> None:
        messages = session.add_all.call_args_list[0].args[0]
        for message in messages:
            message.id = uuid4()

    session.flush.side_effect = assign_message_ids

    result = await persist_rag_exchange(
        organization_id=organization_id,
        conversation_id=conversation.id,
        question="Devam sorusu",
        answer="Devam cevabı",
        sources=[],
        session=session,
    )

    assert result.conversation is conversation
    session.add.assert_not_called()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_rag_exchange_rejects_other_organization_conversation(
    session: AsyncMock,
) -> None:
    session.scalar.return_value = None

    with pytest.raises(ConversationNotFoundError, match="Konuşma bulunamadı"):
        await persist_rag_exchange(
            organization_id=uuid4(),
            conversation_id=uuid4(),
            question="Soru",
            answer="Cevap",
            sources=[],
            session=session,
        )

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_rag_exchange_rolls_back_database_error(session: AsyncMock) -> None:
    session.flush.side_effect = SQLAlchemyError("Database unavailable")

    with pytest.raises(SQLAlchemyError):
        await persist_rag_exchange(
            organization_id=uuid4(),
            conversation_id=None,
            question="Soru",
            answer="Cevap",
            sources=[],
            session=session,
        )

    session.rollback.assert_awaited_once()
