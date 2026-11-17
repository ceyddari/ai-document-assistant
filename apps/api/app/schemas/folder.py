from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

# '@' is the chat mention marker, so it cannot be part of a folder name.
FolderName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50, pattern=r"^[^@]+$"),
]


class FolderCreate(BaseModel):
    name: FolderName


class FolderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime


class FolderListResponse(BaseModel):
    items: list[FolderResponse]


class DocumentMove(BaseModel):
    folder_id: UUID | None
