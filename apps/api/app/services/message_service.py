from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, ConversationDocument, Message, MessageRole, MessageSource
from app.services.conversation_service import (
    ConversationNotFoundError,
    organization_document_ids,
)
from app.services.retrieval_service import RetrievedChunk


@dataclass(frozen=True, slots=True)
class PersistedExchange:
    conversation: Conversation
    user_message: Message
    assistant_message: Message


async def persist_rag_exchange(
    *,
    organization_id: UUID,
    conversation_id: UUID | None,
    question: str,
    answer: str,
    sources: list[RetrievedChunk],
    session: AsyncSession,
    document_ids: list[UUID] | None = None,
) -> PersistedExchange:
    """document_ids becomes the scope of a newly created conversation; ignored otherwise."""
    try:
        if conversation_id is None:
            conversation = Conversation(
                organization_id=organization_id,
                title=question[:255],
            )
            session.add(conversation)
            await session.flush()
            # Documents deleted while the answer streamed are silently left out.
            scope = await organization_document_ids(
                organization_id=organization_id,
                document_ids=document_ids or [],
                session=session,
            )
            if scope:
                session.add_all(
                    [
                        ConversationDocument(
                            conversation_id=conversation.id,
                            document_id=document_id,
                            position=position,
                        )
                        for position, document_id in enumerate(scope)
                    ]
                )
        else:
            statement = (
                select(Conversation)
                .where(
                    Conversation.id == conversation_id,
                    Conversation.organization_id == organization_id,
                )
                .with_for_update()
            )
            conversation = await session.scalar(statement)

            if conversation is None:
                await session.rollback()
                raise ConversationNotFoundError("Konuşma bulunamadı.")

        last_sequence_statement = select(func.max(Message.sequence)).where(
            Message.conversation_id == conversation.id,
            Message.organization_id == organization_id,
        )
        last_sequence = await session.scalar(last_sequence_statement)
        user_sequence = (last_sequence or 0) + 1

        user_message = Message(
            organization_id=organization_id,
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=question,
            sequence=user_sequence,
        )
        assistant_message = Message(
            organization_id=organization_id,
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=answer,
            sequence=user_sequence + 1,
        )
        session.add_all([user_message, assistant_message])
        await session.flush()
        session.add_all(
            [
                MessageSource(
                    organization_id=organization_id,
                    message_id=assistant_message.id,
                    chunk_id=source.chunk_id,
                    similarity=source.similarity,
                    position=position,
                )
                for position, source in enumerate(sources)
            ]
        )
        conversation.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(conversation)
        await session.refresh(user_message)
        await session.refresh(assistant_message)
    except SQLAlchemyError:
        await session.rollback()
        raise

    return PersistedExchange(
        conversation=conversation,
        user_message=user_message,
        assistant_message=assistant_message,
    )
