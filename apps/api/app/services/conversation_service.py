from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Conversation,
    Document,
    DocumentChunk,
    Message,
    MessageRole,
    MessageSource,
    Organization,
)
from app.services.document_service import OrganizationNotFoundError
from app.services.retrieval_service import RetrievedChunk


class ConversationNotFoundError(Exception):
    pass


class MessageNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class MessageWithSources:
    message: Message
    sources: list[RetrievedChunk]


async def create_conversation(
    *,
    organization_id: UUID,
    title: str | None,
    session: AsyncSession,
) -> Conversation:
    organization = await session.get(Organization, organization_id)

    if organization is None:
        raise OrganizationNotFoundError("Organizasyon bulunamadı.")

    conversation = Conversation(
        organization_id=organization_id,
        title=title,
    )
    session.add(conversation)

    try:
        await session.commit()
        await session.refresh(conversation)
    except SQLAlchemyError:
        await session.rollback()
        raise

    return conversation


async def list_conversations(
    *,
    organization_id: UUID,
    session: AsyncSession,
    limit: int,
    offset: int,
) -> tuple[Sequence[Conversation], int]:
    organization = await session.get(Organization, organization_id)

    if organization is None:
        raise OrganizationNotFoundError("Organizasyon bulunamadı.")

    statement = (
        select(Conversation)
        .where(Conversation.organization_id == organization_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    count_statement = (
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.organization_id == organization_id)
    )

    conversations = await session.scalars(statement)
    total = await session.scalar(count_statement)
    return conversations.all(), int(total or 0)


async def get_recent_messages(
    *,
    organization_id: UUID,
    conversation_id: UUID,
    session: AsyncSession,
    limit: int,
) -> list[Message]:
    """Last `limit` messages, oldest first. Raises if the conversation is not in the org."""
    conversation_id_in_organization = await session.scalar(
        select(Conversation.id).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
        )
    )

    if conversation_id_in_organization is None:
        raise ConversationNotFoundError("Konuşma bulunamadı.")

    statement = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.organization_id == organization_id,
        )
        .order_by(Message.sequence.desc())
        .limit(limit)
    )
    messages = list((await session.scalars(statement)).all())
    messages.reverse()
    return messages


async def get_conversation_with_messages(
    *,
    organization_id: UUID,
    conversation_id: UUID,
    session: AsyncSession,
) -> tuple[Conversation, list[MessageWithSources]]:
    conversation_statement = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.organization_id == organization_id,
    )
    conversation = await session.scalar(conversation_statement)

    if conversation is None:
        raise ConversationNotFoundError("Konuşma bulunamadı.")

    messages_statement = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.organization_id == organization_id,
        )
        .order_by(Message.sequence.asc())
    )
    messages = list((await session.scalars(messages_statement)).all())

    if not messages:
        return conversation, []

    source_statement = (
        select(
            MessageSource.message_id,
            DocumentChunk,
            Document.original_filename,
            MessageSource.similarity,
        )
        .join(DocumentChunk, DocumentChunk.id == MessageSource.chunk_id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            MessageSource.message_id.in_([message.id for message in messages]),
            MessageSource.organization_id == organization_id,
        )
        # Stored display order, so [Kaynak N] in the answer matches source N.
        .order_by(MessageSource.position.asc())
    )
    source_rows = (await session.execute(source_statement)).all()
    sources_by_message: dict[UUID, list[RetrievedChunk]] = defaultdict(list)

    for message_id, chunk, filename, similarity in source_rows:
        sources_by_message[message_id].append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                page_number=chunk.page_number,
                content=chunk.content,
                similarity=float(similarity),
            )
        )

    return conversation, [
        MessageWithSources(message=message, sources=sources_by_message[message.id])
        for message in messages
    ]


async def _get_conversation(
    *, organization_id: UUID, conversation_id: UUID, session: AsyncSession
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
        )
    )

    if conversation is None:
        raise ConversationNotFoundError("Konuşma bulunamadı.")

    return conversation


async def rename_conversation(
    *,
    organization_id: UUID,
    conversation_id: UUID,
    title: str,
    session: AsyncSession,
) -> Conversation:
    conversation = await _get_conversation(
        organization_id=organization_id, conversation_id=conversation_id, session=session
    )
    conversation.title = title

    try:
        await session.commit()
        await session.refresh(conversation)
    except SQLAlchemyError:
        await session.rollback()
        raise

    return conversation


async def delete_conversation(
    *,
    organization_id: UUID,
    conversation_id: UUID,
    session: AsyncSession,
) -> None:
    """Messages and their sources go with it (ON DELETE CASCADE)."""
    conversation = await _get_conversation(
        organization_id=organization_id, conversation_id=conversation_id, session=session
    )

    try:
        await session.delete(conversation)
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise


async def set_message_feedback(
    *,
    organization_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    value: int | None,
    session: AsyncSession,
) -> Message:
    message = await session.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.conversation_id == conversation_id,
            Message.organization_id == organization_id,
            Message.role == MessageRole.ASSISTANT,
        )
    )

    if message is None:
        raise MessageNotFoundError("Mesaj bulunamadı.")

    message.feedback = value

    try:
        await session.commit()
        await session.refresh(message)
    except SQLAlchemyError:
        await session.rollback()
        raise

    return message
