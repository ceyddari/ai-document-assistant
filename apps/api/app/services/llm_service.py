import asyncio

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from app.core.config import Settings


class LlmServiceError(Exception):
    pass


class LlmService:
    def __init__(self, *, settings: Settings) -> None:
        self._model = ChatOllama(
            model=settings.ollama_llm_model,
            base_url=settings.ollama_base_url,
            temperature=0,
        )
        self._timeout_seconds = settings.ollama_timeout_seconds

    async def generate_answer(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._model.ainvoke(
                    [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_prompt),
                    ]
                )
        except TimeoutError as error:
            raise LlmServiceError("Dil modeli isteği zaman aşımına uğradı.") from error
        except Exception as error:
            raise LlmServiceError("Dil modeli cevap üretemedi.") from error

        content = response.content

        if not isinstance(content, str) or not content.strip():
            raise LlmServiceError("Dil modeli boş bir cevap döndürdü.")

        return content.strip()
