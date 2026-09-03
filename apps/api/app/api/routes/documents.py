from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import AppSettings, DatabaseSession
from app.schemas import DocumentListResponse, DocumentResponse
from app.services import (
    DocumentNotFoundError,
    DocumentTooLargeError,
    InvalidPdfError,
    OrganizationNotFoundError,
    create_document,
    get_document_by_id,
    list_documents,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/documents",
    tags=["documents"],
)


@router.get(
    "",
    response_model=DocumentListResponse,
)
async def get_documents(
    organization_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    try:
        documents, total = await list_documents(
            organization_id=organization_id,
            session=session,
            limit=limit,
            offset=offset,
        )

    except OrganizationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dokümanlar şu anda getirilemiyor.",
        ) from error

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
async def get_document(
    organization_id: UUID,
    document_id: UUID,
    session: DatabaseSession,
) -> DocumentResponse:
    try:
        document = await get_document_by_id(
            organization_id=organization_id,
            document_id=document_id,
            session=session,
        )

    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Doküman şu anda getirilemiyor.",
        ) from error

    return DocumentResponse.model_validate(document)


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
