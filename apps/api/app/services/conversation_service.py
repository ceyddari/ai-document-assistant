from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Document, DocumentChunk, Message, MessageSource, Organization
from app.services.document_service import OrganizationNotFoundError
from app.services.retrieval_service import RetrievedChunk


class ConversationNotFoundError(Exception):
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
        .order_by(Message.created_at.asc(), Message.id.asc())
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
        .order_by(MessageSource.created_at.asc(), MessageSource.id.asc())
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
