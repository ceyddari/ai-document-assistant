from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DatabaseSession, require_organization_member
from app.schemas import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    MessageResponse,
    RetrievedChunkResponse,
)
from app.services import (
    ConversationNotFoundError,
    OrganizationNotFoundError,
    create_conversation,
    get_conversation_with_messages,
    list_conversations,
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
    except OrganizationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Konuşmalar şu anda getirilemiyor.") from error

    return ConversationListResponse(
        items=[ConversationResponse.model_validate(item) for item in conversations],
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
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Konuşma şu anda getirilemiyor.") from error

    response = ConversationResponse.model_validate(conversation)
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
