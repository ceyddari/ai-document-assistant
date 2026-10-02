from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import AppSettings, DatabaseSession
from app.schemas import AskRequest, AskResponse, RetrievedChunkResponse
from app.services import (
    ConversationNotFoundError,
    EmbeddingService,
    EmbeddingServiceError,
    LlmService,
    LlmServiceError,
    OrganizationNotFoundError,
    answer_question,
    persist_rag_exchange,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/ask",
    tags=["rag"],
)


@router.post("", response_model=AskResponse)
async def ask_question(
    organization_id: UUID,
    request: AskRequest,
    session: DatabaseSession,
    settings: AppSettings,
) -> AskResponse:
    embedding_service = EmbeddingService(settings=settings)
    llm_service = LlmService(settings=settings)

    try:
        result = await answer_question(
            organization_id=organization_id,
            question=request.question,
            session=session,
            embedding_service=embedding_service,
            llm_service=llm_service,
            limit=request.limit,
            minimum_similarity=settings.retrieval_min_similarity,
        )
        exchange = await persist_rag_exchange(
            organization_id=organization_id,
            conversation_id=request.conversation_id,
            question=request.question,
            answer=result.answer,
            sources=result.sources,
            session=session,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except OrganizationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except EmbeddingServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding servisine şu anda erişilemiyor.",
        ) from error
    except LlmServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dil modeli servisine şu anda erişilemiyor.",
        ) from error
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Soru şu anda yanıtlanamıyor.",
        ) from error

    return AskResponse(
        conversation_id=exchange.conversation.id,
        user_message_id=exchange.user_message.id,
        assistant_message_id=exchange.assistant_message.id,
        question=request.question,
        answer=result.answer,
        sources=[
            RetrievedChunkResponse(
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                filename=source.filename,
                page_number=source.page_number,
                content=source.content,
                similarity=source.similarity,
            )
            for source in result.sources
        ],
    )
