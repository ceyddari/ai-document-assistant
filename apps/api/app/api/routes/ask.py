import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AppSettings, DatabaseSession, require_organization_member
from app.db.session import get_session_factory
from app.schemas import AskRequest, AskResponse, RetrievedChunkResponse
from app.services import (
    ConversationNotFoundError,
    EmbeddingService,
    EmbeddingServiceError,
    HistoryMessage,
    LlmService,
    LlmServiceError,
    OrganizationNotFoundError,
    PersistedExchange,
    RagAnswer,
    answer_question,
    get_recent_messages,
    persist_rag_exchange,
    stream_answer_question,
)
from app.services.rag_service import HISTORY_MESSAGE_LIMIT

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/organizations/{organization_id}/ask",
    tags=["rag"],
    dependencies=[Depends(require_organization_member)],
)


def _error_response(error: Exception) -> tuple[int, str] | None:
    """Status and user-facing message for an expected failure; None for anything else."""
    if isinstance(error, (ConversationNotFoundError, OrganizationNotFoundError)):
        return status.HTTP_404_NOT_FOUND, str(error)
    if isinstance(error, EmbeddingServiceError):
        return status.HTTP_503_SERVICE_UNAVAILABLE, "Embedding servisine şu anda erişilemiyor."
    if isinstance(error, LlmServiceError):
        return status.HTTP_503_SERVICE_UNAVAILABLE, "Dil modeli servisine şu anda erişilemiyor."
    if isinstance(error, SQLAlchemyError):
        return status.HTTP_503_SERVICE_UNAVAILABLE, "Soru şu anda yanıtlanamıyor."
    return None


async def _load_history(
    *,
    organization_id: UUID,
    request: AskRequest,
    session: AsyncSession,
) -> list[HistoryMessage]:
    # Checked before any model call, so an unknown conversation fails fast with 404.
    if request.conversation_id is None:
        return []

    messages = await get_recent_messages(
        organization_id=organization_id,
        conversation_id=request.conversation_id,
        session=session,
        limit=HISTORY_MESSAGE_LIMIT,
    )
    return [
        HistoryMessage(role=message.role.value, content=message.content) for message in messages
    ]


def _ask_response(
    *,
    request: AskRequest,
    result: RagAnswer,
    exchange: PersistedExchange,
) -> AskResponse:
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
        history = await _load_history(
            organization_id=organization_id, request=request, session=session
        )
        result = await answer_question(
            organization_id=organization_id,
            question=request.question,
            session=session,
            embedding_service=embedding_service,
            llm_service=llm_service,
            history=history,
            document_ids=request.document_ids,
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
    except Exception as error:
        mapped = _error_response(error)
        if mapped is None:
            raise
        raise HTTPException(status_code=mapped[0], detail=mapped[1]) from error

    return _ask_response(request=request, result=result, exchange=exchange)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def ask_question_stream(
    organization_id: UUID,
    request: AskRequest,
    session: DatabaseSession,
    settings: AppSettings,
) -> StreamingResponse:
    """Server-sent events: {"type": "token", "text"}* then {"type": "done", ...AskResponse}.

    Failures after the stream started arrive as {"type": "error", "detail"}, because the HTTP
    status is already sent. If the client disconnects (stop button), the generator is
    cancelled and nothing is saved.
    """
    try:
        history = await _load_history(
            organization_id=organization_id, request=request, session=session
        )
    except Exception as error:
        mapped = _error_response(error)
        if mapped is None:
            raise
        raise HTTPException(status_code=mapped[0], detail=mapped[1]) from error

    embedding_service = EmbeddingService(settings=settings)
    llm_service = LlmService(settings=settings)

    async def events() -> AsyncIterator[str]:
        # Own session: the request-scoped one may already be closed while the body streams.
        async with get_session_factory()() as stream_session:
            try:
                result: RagAnswer | None = None

                async for item in stream_answer_question(
                    organization_id=organization_id,
                    question=request.question,
                    session=stream_session,
                    embedding_service=embedding_service,
                    llm_service=llm_service,
                    history=history,
                    document_ids=request.document_ids,
                    limit=request.limit,
                    minimum_similarity=settings.retrieval_min_similarity,
                ):
                    if isinstance(item, str):
                        yield _sse({"type": "token", "text": item})
                    else:
                        result = item

                if result is None:
                    raise LlmServiceError("Cevap tamamlanmadı.")

                exchange = await persist_rag_exchange(
                    organization_id=organization_id,
                    conversation_id=request.conversation_id,
                    question=request.question,
                    answer=result.answer,
                    sources=result.sources,
                    session=stream_session,
                )
                response = _ask_response(request=request, result=result, exchange=exchange)
                yield _sse({"type": "done", **response.model_dump(mode="json")})
            except Exception as error:
                mapped = _error_response(error)

                if mapped is None:
                    logger.exception("Akışlı cevap beklenmeyen bir hatayla kesildi.")

                yield _sse(
                    {
                        "type": "error",
                        "detail": mapped[1] if mapped else "Soru şu anda yanıtlanamıyor.",
                    }
                )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # no-transform/X-Accel-Buffering: keep proxies from buffering the whole answer.
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
