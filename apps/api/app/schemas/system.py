from pydantic import BaseModel


class AiReadinessResponse(BaseModel):
    status: str
    embedding_model: str
    llm_model: str
