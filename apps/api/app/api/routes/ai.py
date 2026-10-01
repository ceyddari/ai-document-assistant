from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import AppSettings
from app.schemas import AiReadinessResponse
from app.services import AiReadinessError, check_ai_readiness

router = APIRouter(
    prefix="/ai",
    tags=["system"],
)


@router.get(
    "/readiness",
    response_model=AiReadinessResponse,
)
async def ai_readiness(settings: AppSettings) -> AiReadinessResponse:
    try:
        readiness = await check_ai_readiness(settings=settings)
    except AiReadinessError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    return AiReadinessResponse(
        status="ready",
        embedding_model=readiness.embedding_model,
        llm_model=readiness.llm_model,
    )
