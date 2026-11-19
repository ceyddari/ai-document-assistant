import asyncio
from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, ValidationError

from app.core.config import Settings


class LlmServiceError(Exception):
    pass


class LlmService:
    def __init__(self, *, settings: Settings) -> None:
        self._model = ChatOllama(
            model=settings.ollama_llm_model,
            base_url=settings.ollama_base_url,
            temperature=0,
            # Source-grounded short answers don't need Qwen3's thinking step; it only adds latency.
            reasoning=False,
            keep_alive=settings.ollama_keep_alive_seconds,
            num_ctx=settings.ollama_llm_num_ctx,
        )
        self._timeout_seconds = settings.ollama_timeout_seconds

    async def generate_answer(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        reasoning: bool = False,
        response_format: dict | None = None,
    ) -> str:
        options = {"reasoning": True} if reasoning else {}
        if response_format is not None:
            options["format"] = response_format
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._model.ainvoke(
                    [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_prompt),
                    ],
                    **options,
                )
        except TimeoutError as error:
            raise LlmServiceError("Dil modeli isteği zaman aşımına uğradı.") from error
        except Exception as error:
            raise LlmServiceError("Dil modeli cevap üretemedi.") from error

        content = response.content

        if not isinstance(content, str) or not content.strip():
            raise LlmServiceError("Dil modeli boş bir cevap döndürdü.")

        return content.strip()

    async def generate_structured[T: BaseModel](
        self, *, system_prompt: str, user_prompt: str, schema: type[T]
    ) -> T:
        content = await self.generate_answer(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=schema.model_json_schema(),
        )
        try:
            return schema.model_validate_json(content)
        except ValidationError as error:
            raise LlmServiceError("Dil modeli beklenen cevap biçimini döndürmedi.") from error

    async def stream_answer(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        reasoning: bool = False,
    ) -> AsyncIterator[str]:
        """Yield answer text as the model produces it; the timeout covers the whole stream.

        Cancellation (client disconnect) is not caught, so the Ollama request is closed too.
        """
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async for chunk in self._model.astream(
                    [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_prompt),
                    ],
                    **({"reasoning": True} if reasoning else {}),
                ):
                    if isinstance(chunk.content, str) and chunk.content:
                        yield chunk.content
        except TimeoutError as error:
            raise LlmServiceError("Dil modeli isteği zaman aşımına uğradı.") from error
        except Exception as error:
            raise LlmServiceError("Dil modeli cevap üretemedi.") from error
