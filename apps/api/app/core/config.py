from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr
    postgres_host: str
    postgres_port: int

    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "bge-m3"
    ollama_llm_model: str = "qwen3:8b"
    ollama_timeout_seconds: float = Field(default=120, gt=0)
    # Ollama unloads idle models after 5 minutes; the next question then pays a cold load.
    ollama_keep_alive_seconds: int = Field(default=1800, ge=-1)
    # Ollama's default context is small; 20 sources x 1000 chars would be silently truncated.
    ollama_llm_num_ctx: int = Field(default=8192, ge=2048)
    # 0 runs embeddings on CPU: on small GPUs (8 GB) the LLM and bge-m3 do not fit together,
    # so each question would evict and reload the LLM (~5 s). None lets Ollama decide.
    ollama_embedding_num_gpu: int | None = Field(default=None, ge=0)
    ollama_embedding_batch_size: int = Field(default=16, ge=1, le=256)
    ollama_embedding_max_retries: int = Field(default=3, ge=0, le=10)
    ollama_embedding_retry_delay_seconds: float = Field(default=1, ge=0, le=60)
    retrieval_min_similarity: float = Field(default=0.35, ge=0, le=1)
    rag_rerank_enabled: bool = False
    rag_verify_citations: bool = True
    rag_complex_questions: bool = True
    rag_adaptive_quality: bool = True
    # Summarize every section once after upload so summaries cover the whole document.
    rag_section_summaries: bool = True

    storage_directory: Path = Path("storage/documents")
    max_upload_size_mb: int = 10
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
