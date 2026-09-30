from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

SearchQuery = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=2000,
    ),
]


class SemanticSearchRequest(BaseModel):
    query: SearchQuery
    limit: int = Field(default=5, ge=1, le=20)


class RetrievedChunkResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int
    content: str
    similarity: float


class SemanticSearchResponse(BaseModel):
    query: str
    items: list[RetrievedChunkResponse]
