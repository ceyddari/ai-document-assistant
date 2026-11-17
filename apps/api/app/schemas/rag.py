from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievedChunkResponse, SearchQuery


class AskRequest(BaseModel):
    question: SearchQuery
    limit: int = Field(default=5, ge=1, le=20)
    conversation_id: UUID | None = None
    # Restrict retrieval to these documents; null or empty means all documents.
    document_ids: list[UUID] | None = Field(default=None, max_length=100)


class AskResponse(BaseModel):
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    question: str
    answer: str
    sources: list[RetrievedChunkResponse]
