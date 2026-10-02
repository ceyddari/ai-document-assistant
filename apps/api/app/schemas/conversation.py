from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models import MessageRole
from app.schemas.retrieval import RetrievedChunkResponse

ConversationTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class ConversationCreate(BaseModel):
    title: ConversationTitle | None = None

    @field_validator("title", mode="before")
    @classmethod
    def normalize_blank_title(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    created_at: datetime
    sources: list[RetrievedChunkResponse] = Field(default_factory=list)


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = Field(default_factory=list)
