import logging
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import AppSettings, DatabaseSession, require_organization_member
from app.schemas import DocumentListResponse, DocumentResponse
from app.schemas.folder import DocumentMove
from app.services import (
    DocumentBusyError,
    DocumentNotFoundError,
    DocumentNotRetryableError,
    DocumentTooLargeError,
    FolderNotFoundError,
    InvalidPdfError,
    OrganizationNotFoundError,
    create_document,
    delete_document,
    get_document_by_id,
    list_documents,
    move_document,
    prepare_document_retry,
    resolve_document_file,
)
from app.tasks.document_tasks import process_document_in_background

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/organizations/{organization_id}/documents",
    tags=["documents"],
    dependencies=[Depends(require_organization_member)],
)


@router.post(
    "/{document_id}/retry",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_document_processing(
    organization_id: UUID,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    session: DatabaseSession,
) -> DocumentResponse:
    try:
        document = await prepare_document_retry(
            organization_id=organization_id,
            document_id=document_id,
            session=session,
        )
        background_tasks.add_task(process_document_in_background, document.id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DocumentNotRetryableError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503,
            detail="Doküman şu anda yeniden işlenemiyor.",
        ) from error

    return DocumentResponse.model_validate(document)


@router.get(
    "",
    response_model=DocumentListResponse,
)
async def get_documents(
    organization_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    folder_id: UUID | None = None,
) -> DocumentListResponse:
    try:
        documents, total = await list_documents(
            organization_id=organization_id,
            session=session,
            limit=limit,
            offset=offset,
            folder_id=folder_id,
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
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    session: DatabaseSession,
    settings: AppSettings,
    folder_id: Annotated[UUID | None, Form()] = None,
) -> DocumentResponse:
    try:
        document = await create_document(
            file=file,
            organization_id=organization_id,
            session=session,
            settings=settings,
            folder_id=folder_id,
        )

        background_tasks.add_task(
            process_document_in_background,
            document.id,
        )

    except (OrganizationNotFoundError, FolderNotFoundError) as error:
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


@router.patch("/{document_id}", response_model=DocumentResponse)
async def move_organization_document(
    organization_id: UUID,
    document_id: UUID,
    request: DocumentMove,
    session: DatabaseSession,
) -> DocumentResponse:
    try:
        document = await get_document_by_id(
            organization_id=organization_id, document_id=document_id, session=session
        )
        document = await move_document(
            document=document, folder_id=request.folder_id, session=session
        )
    except (DocumentNotFoundError, FolderNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Doküman şu anda taşınamıyor.") from error

    return DocumentResponse.model_validate(document)


@router.get("/{document_id}/file", response_class=FileResponse)
async def get_document_file(
    organization_id: UUID,
    document_id: UUID,
    session: DatabaseSession,
    settings: AppSettings,
) -> FileResponse:
    try:
        document = await get_document_by_id(
            organization_id=organization_id, document_id=document_id, session=session
        )
        path = resolve_document_file(document=document, settings=settings)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Doküman şu anda açılamıyor.") from error

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document.original_filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization_document(
    organization_id: UUID,
    document_id: UUID,
    session: DatabaseSession,
    settings: AppSettings,
) -> Response:
    try:
        storage_path = await delete_document(
            organization_id=organization_id, document_id=document_id, session=session
        )
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DocumentBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Doküman şu anda silinemiyor.") from error

    # The row is gone; a leftover file is only wasted disk, so a failure here is not an error.
    resolved = storage_path.resolve()
    if resolved.is_relative_to(settings.storage_directory.resolve()):
        try:
            resolved.unlink(missing_ok=True)
        except OSError:
            logger.warning("Silinen dokümanın dosyası kaldırılamadı: %s", resolved)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
