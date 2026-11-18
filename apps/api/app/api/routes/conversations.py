from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DatabaseSession, require_organization_member
from app.schemas import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationDocumentsUpdate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageFeedbackUpdate,
    MessageResponse,
    RetrievedChunkResponse,
)
from app.services import (
    ConversationNotFoundError,
    DocumentNotFoundError,
    MessageNotFoundError,
    OrganizationNotFoundError,
    conversation_document_ids,
    create_conversation,
    delete_conversation,
    get_conversation_with_messages,
    list_conversations,
    rename_conversation,
    set_conversation_documents,
    set_message_feedback,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/conversations",
    tags=["conversations"],
    dependencies=[Depends(require_organization_member)],
)


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization_conversation(
    organization_id: UUID,
    request: ConversationCreate,
    session: DatabaseSession,
) -> ConversationResponse:
    try:
        conversation = await create_conversation(
            organization_id=organization_id,
            title=request.title,
            session=session,
        )
    except OrganizationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Konuşma şu anda oluşturulamıyor.") from error

    return ConversationResponse.model_validate(conversation)


@router.get("", response_model=ConversationListResponse)
async def get_conversations(
    organization_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationListResponse:
    try:
        conversations, total = await list_conversations(
            organization_id=organization_id,
            session=session,
            limit=limit,
            offset=offset,
        )
        scopes = await conversation_document_ids(
            conversation_ids=[item.id for item in conversations], session=session
        )
    except OrganizationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Konuşmalar şu anda getirilemiyor.") from error

    return ConversationListResponse(
        items=[
            ConversationResponse.model_validate(item).model_copy(
                update={"document_ids": scopes.get(item.id, [])}
            )
            for item in conversations
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    organization_id: UUID,
    conversation_id: UUID,
    session: DatabaseSession,
) -> ConversationDetailResponse:
    try:
        conversation, messages = await get_conversation_with_messages(
            organization_id=organization_id,
            conversation_id=conversation_id,
            session=session,
        )
        scopes = await conversation_document_ids(
            conversation_ids=[conversation.id], session=session
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Konuşma şu anda getirilemiyor.") from error

    response = ConversationResponse.model_validate(conversation).model_copy(
        update={"document_ids": scopes.get(conversation.id, [])}
    )
    return ConversationDetailResponse(
        **response.model_dump(),
        messages=[
            MessageResponse(
                **MessageResponse.model_validate(item.message).model_dump(exclude={"sources"}),
                sources=[
                    RetrievedChunkResponse(
                        chunk_id=source.chunk_id,
                        document_id=source.document_id,
                        filename=source.filename,
                        page_number=source.page_number,
                        content=source.content,
                        similarity=source.similarity,
                    )
                    for source in item.sources
                ],
            )
            for item in messages
        ],
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def rename_organization_conversation(
    organization_id: UUID,
    conversation_id: UUID,
    request: ConversationUpdate,
    session: DatabaseSession,
) -> ConversationResponse:
    try:
        conversation = await rename_conversation(
            organization_id=organization_id,
            conversation_id=conversation_id,
            title=request.title,
            session=session,
        )
        scopes = await conversation_document_ids(
            conversation_ids=[conversation.id], session=session
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Konuşma şu anda güncellenemiyor.") from error

    return ConversationResponse.model_validate(conversation).model_copy(
        update={"document_ids": scopes.get(conversation.id, [])}
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization_conversation(
    organization_id: UUID,
    conversation_id: UUID,
    session: DatabaseSession,
) -> Response:
    try:
        await delete_conversation(
            organization_id=organization_id,
            conversation_id=conversation_id,
            session=session,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Konuşma şu anda silinemiyor.") from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{conversation_id}/messages/{message_id}/feedback", response_model=MessageResponse)
async def update_message_feedback(
    organization_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    request: MessageFeedbackUpdate,
    session: DatabaseSession,
) -> MessageResponse:
    try:
        message = await set_message_feedback(
            organization_id=organization_id,
            conversation_id=conversation_id,
            message_id=message_id,
            value=request.value,
            session=session,
        )
    except MessageNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503, detail="Geri bildirim şu anda kaydedilemiyor."
        ) from error

    return MessageResponse.model_validate(message)


@router.put("/{conversation_id}/documents", response_model=list[UUID])
async def update_conversation_documents(
    organization_id: UUID,
    conversation_id: UUID,
    request: ConversationDocumentsUpdate,
    session: DatabaseSession,
) -> list[UUID]:
    """Replace the documents this conversation is limited to; [] lifts the limit."""
    try:
        return await set_conversation_documents(
            organization_id=organization_id,
            conversation_id=conversation_id,
            document_ids=request.document_ids,
            session=session,
        )
    except (ConversationNotFoundError, DocumentNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503, detail="Konuşmanın dokümanları şu anda güncellenemiyor."
        ) from error
