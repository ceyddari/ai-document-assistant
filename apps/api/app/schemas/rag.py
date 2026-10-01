from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievedChunkResponse, SearchQuery


class AskRequest(BaseModel):
    question: SearchQuery
    limit: int = Field(default=5, ge=1, le=20)


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[RetrievedChunkResponse]
