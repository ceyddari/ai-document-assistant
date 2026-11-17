import re
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, Folder


class FolderNotFoundError(Exception):
    pass


class FolderNameTakenError(Exception):
    pass


async def list_folders(*, organization_id: UUID, session: AsyncSession) -> Sequence[Folder]:
    result = await session.scalars(
        select(Folder).where(Folder.organization_id == organization_id).order_by(Folder.name)
    )
    return result.all()


async def create_folder(*, organization_id: UUID, name: str, session: AsyncSession) -> Folder:
    folder = Folder(organization_id=organization_id, name=name)
    session.add(folder)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise FolderNameTakenError("Bu isimde bir klasör zaten var.") from error
    await session.refresh(folder)
    return folder


async def get_folder(*, organization_id: UUID, folder_id: UUID, session: AsyncSession) -> Folder:
    folder = await session.scalar(
        select(Folder).where(Folder.id == folder_id, Folder.organization_id == organization_id)
    )
    if folder is None:
        raise FolderNotFoundError("Klasör bulunamadı.")
    return folder


async def delete_folder(*, organization_id: UUID, folder_id: UUID, session: AsyncSession) -> None:
    # Documents are kept: the DB sets their folder_id to NULL.
    folder = await get_folder(organization_id=organization_id, folder_id=folder_id, session=session)
    await session.delete(folder)
    await session.commit()


async def move_document(
    *, document: Document, folder_id: UUID | None, session: AsyncSession
) -> Document:
    if folder_id is not None:
        await get_folder(
            organization_id=document.organization_id, folder_id=folder_id, session=session
        )
    document.folder_id = folder_id
    await session.commit()
    await session.refresh(document)
    return document


async def resolve_folder_mentions(
    *, organization_id: UUID, text: str, session: AsyncSession
) -> tuple[list[UUID], str]:
    """Find `@Klasör Adı` mentions. Returns (folder ids, text with mentions removed)."""
    folders = sorted(
        await list_folders(organization_id=organization_id, session=session),
        key=lambda folder: len(folder.name),
        reverse=True,  # longest first so "@Finans Raporları" wins over "@Finans"
    )
    ids: list[UUID] = []
    for folder in folders:
        pattern = re.compile(rf"(?<!\w)@{re.escape(folder.name)}(?!\w)", re.IGNORECASE)
        if pattern.search(text):
            ids.append(folder.id)
            text = pattern.sub(" ", text)
    return ids, " ".join(text.split())
