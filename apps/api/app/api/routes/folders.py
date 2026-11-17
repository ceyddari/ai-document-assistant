from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DatabaseSession, require_organization_member
from app.schemas.folder import FolderCreate, FolderListResponse, FolderResponse
from app.services.folder_service import (
    FolderNameTakenError,
    FolderNotFoundError,
    create_folder,
    delete_folder,
    list_folders,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/folders",
    tags=["folders"],
    dependencies=[Depends(require_organization_member)],
)


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Klasörler şu anda kullanılamıyor.")


@router.get("", response_model=FolderListResponse)
async def get_folders(organization_id: UUID, session: DatabaseSession) -> FolderListResponse:
    try:
        folders = await list_folders(organization_id=organization_id, session=session)
    except SQLAlchemyError as error:
        raise _unavailable() from error
    return FolderListResponse(items=[FolderResponse.model_validate(item) for item in folders])


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_organization_folder(
    organization_id: UUID, request: FolderCreate, session: DatabaseSession
) -> FolderResponse:
    try:
        folder = await create_folder(
            organization_id=organization_id, name=request.name, session=session
        )
    except FolderNameTakenError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise _unavailable() from error
    return FolderResponse.model_validate(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization_folder(
    organization_id: UUID, folder_id: UUID, session: DatabaseSession
) -> Response:
    try:
        await delete_folder(organization_id=organization_id, folder_id=folder_id, session=session)
    except FolderNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise _unavailable() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
