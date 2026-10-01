from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import AppSettings, DatabaseSession
from app.schemas import (
    RetrievedChunkResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from app.services import (
    EmbeddingService,
    EmbeddingServiceError,
    OrganizationNotFoundError,
    search_relevant_chunks,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/search",
    tags=["search"],
)


@router.post(
    "",
    response_model=SemanticSearchResponse,
)
async def semantic_search(
    organization_id: UUID,
    request: SemanticSearchRequest,
    session: DatabaseSession,
    settings: AppSettings,
) -> SemanticSearchResponse:
    embedding_service = EmbeddingService(settings=settings)

    try:
        chunks = await search_relevant_chunks(
            organization_id=organization_id,
            query=request.query,
            session=session,
            embedding_service=embedding_service,
            limit=request.limit,
            minimum_similarity=settings.retrieval_min_similarity,
        )

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

    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Semantik arama şu anda gerçekleştirilemiyor.",
        ) from error

    return SemanticSearchResponse(
        query=request.query,
        items=[
            RetrievedChunkResponse(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                filename=chunk.filename,
                page_number=chunk.page_number,
                content=chunk.content,
                similarity=chunk.similarity,
            )
            for chunk in chunks
        ],
    )
