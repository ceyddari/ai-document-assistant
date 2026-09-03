from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import AppSettings, DatabaseSession
from app.schemas import DocumentResponse
from app.services import (
    DocumentTooLargeError,
    InvalidPdfError,
    OrganizationNotFoundError,
    create_document,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/documents",
    tags=["documents"],
)


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    organization_id: UUID,
    file: Annotated[UploadFile, File(...)],
    session: DatabaseSession,
    settings: AppSettings,
) -> DocumentResponse:
    try:
        document = await create_document(
            file=file,
            organization_id=organization_id,
            session=session,
            settings=settings,
        )

    except OrganizationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except InvalidPdfError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    except DocumentTooLargeError as error:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(error),
        ) from error

    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Doküman şu anda kaydedilemiyor.",
        ) from error

    return DocumentResponse.model_validate(document)
