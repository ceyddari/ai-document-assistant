import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import Conversation, Message
from app.services import (
    NO_RELEVANT_SOURCE_ANSWER,
    ConversationNotFoundError,
    LlmService,
    LlmServiceError,
    PersistedExchange,
    RagAnswer,
    RetrievedChunk,
    stream_answer_question,
)


def build_source() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="policy.pdf",
        page_number=3,
        content="İzin 14 gündür.",
        similarity=0.8,
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        postgres_db="test_database",
        postgres_user="test_user",
        postgres_password="test_password",
        postgres_host="localhost",
        postgres_port=5432,
    )


@pytest.fixture
def db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def stream_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def client(
    db_session: AsyncMock,
    stream_session: AsyncMock,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    @asynccontextmanager
    async def open_stream_session() -> AsyncIterator[AsyncSession]:
        yield stream_session

    monkeypatch.setattr("app.api.routes.ask.get_session_factory", lambda: open_stream_session)
    monkeypatch.setattr("app.api.routes.ask.EmbeddingService", MagicMock())
    monkeypatch.setattr("app.api.routes.ask.LlmService", MagicMock())
    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def persist_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    conversation = MagicMock(spec=Conversation)
    conversation.id = uuid4()
    user_message = MagicMock(spec=Message)
    user_message.id = uuid4()
    assistant_message = MagicMock(spec=Message)
    assistant_message.id = uuid4()
    mock = AsyncMock(
        return_value=PersistedExchange(
            conversation=conversation,
            user_message=user_message,
            assistant_message=assistant_message,
        )
    )
    monkeypatch.setattr("app.api.routes.ask.persist_rag_exchange", mock)
    return mock


def fake_stream(*items: str | RagAnswer | Exception):
    async def generator(**_: object) -> AsyncIterator[str | RagAnswer]:
        for item in items:
            if isinstance(item, Exception):
                raise item
            yield item

    return generator


def parse_events(body: str) -> list[dict]:
    return [
        json.loads(block.removeprefix("data: "))
        for block in body.split("\n\n")
        if block.startswith("data: ")
    ]


def test_stream_sends_tokens_then_done_and_persists_final_answer(
    client: TestClient,
    stream_session: AsyncMock,
    persist_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = build_source()
    final = RagAnswer(answer="İzin 14 gündür [Kaynak 1].", sources=[source])
    monkeypatch.setattr(
        "app.api.routes.ask.stream_answer_question",
        fake_stream("İzin 14 ", "gündür [Kaynak 3].", final),
    )

    response = client.post(
        f"/organizations/{uuid4()}/ask/stream",
        json={"question": "İzin kaç gün?", "document_ids": [str(source.document_id)]},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_events(response.text)
    assert [event["type"] for event in events] == ["token", "token", "done"]
    assert "".join(event["text"] for event in events[:2]) == "İzin 14 gündür [Kaynak 3]."
    # The done event carries the checked, renumbered answer that replaces the streamed text.
    assert events[2]["answer"] == "İzin 14 gündür [Kaynak 1]."
    assert events[2]["sources"][0]["chunk_id"] == str(source.chunk_id)
    assert persist_mock.await_args.kwargs["answer"] == final.answer
    assert persist_mock.await_args.kwargs["session"] is stream_session


def test_stream_without_sources_sends_only_done(
    client: TestClient,
    persist_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.ask.stream_answer_question",
        fake_stream(RagAnswer(answer=NO_RELEVANT_SOURCE_ANSWER, sources=[])),
    )

    response = client.post(f"/organizations/{uuid4()}/ask/stream", json={"question": "Soru"})

    events = parse_events(response.text)
    assert [event["type"] for event in events] == ["done"]
    assert events[0]["answer"] == NO_RELEVANT_SOURCE_ANSWER


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (LlmServiceError("down"), "Dil modeli servisine şu anda erişilemiyor."),
        (RuntimeError("bug"), "Soru şu anda yanıtlanamıyor."),
    ],
)
def test_stream_reports_failures_as_error_event_and_saves_nothing(
    client: TestClient,
    persist_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    detail: str,
) -> None:
    monkeypatch.setattr("app.api.routes.ask.stream_answer_question", fake_stream("Yarım ", error))

    response = client.post(f"/organizations/{uuid4()}/ask/stream", json={"question": "Soru"})

    events = parse_events(response.text)
    assert [event["type"] for event in events] == ["token", "error"]
    assert events[1]["detail"] == detail
    persist_mock.assert_not_awaited()


def test_stream_rejects_unknown_conversation_before_streaming(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_mock = MagicMock()
    monkeypatch.setattr("app.api.routes.ask.stream_answer_question", stream_mock)
    monkeypatch.setattr(
        "app.api.routes.ask.get_recent_messages",
        AsyncMock(side_effect=ConversationNotFoundError("Konuşma bulunamadı.")),
    )

    response = client.post(
        f"/organizations/{uuid4()}/ask/stream",
        json={"question": "Peki?", "conversation_id": str(uuid4())},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Konuşma bulunamadı."}
    stream_mock.assert_not_called()


@pytest.mark.asyncio
async def test_stream_answer_question_yields_text_then_checked_answer() -> None:
    sources = [build_source(), build_source()]
    llm_service = MagicMock()

    async def model_stream(**_: object) -> AsyncIterator[str]:
        for text in ("Cevap ", "[Kaynak 2]."):
            yield text

    llm_service.stream_answer = model_stream

    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=([], "Soru")),
        ),
        patch(
            "app.services.rag_service.search_relevant_chunks",
            new=AsyncMock(return_value=sources),
        ) as search_mock,
    ):
        items = [
            item
            async for item in stream_answer_question(
                organization_id=uuid4(),
                question="Soru",
                session=AsyncMock(spec=AsyncSession),
                embedding_service=MagicMock(),
                llm_service=llm_service,
                document_ids=[sources[1].document_id],
            )
        ]

    assert items[:2] == ["Cevap ", "[Kaynak 2]."]
    assert items[2] == RagAnswer(answer="Cevap [Kaynak 1].", sources=[sources[1]])
    assert search_mock.await_args.kwargs["document_ids"] == [sources[1].document_id]


@pytest.mark.asyncio
async def test_stream_answer_question_rejects_empty_model_output() -> None:
    llm_service = MagicMock()

    async def model_stream(**_: object) -> AsyncIterator[str]:
        yield "   "

    llm_service.stream_answer = model_stream

    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=([], "Soru")),
        ),
        patch(
            "app.services.rag_service.search_relevant_chunks",
            new=AsyncMock(return_value=[build_source()]),
        ),
        pytest.raises(LlmServiceError),
    ):
        async for _ in stream_answer_question(
            organization_id=uuid4(),
            question="Soru",
            session=AsyncMock(spec=AsyncSession),
            embedding_service=MagicMock(),
            llm_service=llm_service,
        ):
            pass


@pytest.mark.asyncio
async def test_llm_stream_answer_yields_text_and_maps_errors(settings: Settings) -> None:
    def chunk(text: str) -> MagicMock:
        return MagicMock(content=text)

    async def ok_stream(_: object) -> AsyncIterator[MagicMock]:
        for text in ("A", "", "B"):
            yield chunk(text)

    async def broken_stream(_: object) -> AsyncIterator[MagicMock]:
        yield chunk("A")
        raise ConnectionError("ollama gone")

    async def slow_stream(_: object) -> AsyncIterator[MagicMock]:
        await asyncio.sleep(1)
        yield chunk("late")

    with patch("app.services.llm_service.ChatOllama") as model_constructor:
        model = MagicMock()
        model_constructor.return_value = model
        service = LlmService(settings=settings.model_copy(update={"ollama_timeout_seconds": 0.05}))

        model.astream = ok_stream
        assert [
            text async for text in service.stream_answer(system_prompt="s", user_prompt="u")
        ] == [
            "A",
            "B",
        ]

        model.astream = broken_stream
        with pytest.raises(LlmServiceError, match="cevap üretemedi"):
            async for _ in service.stream_answer(system_prompt="s", user_prompt="u"):
                pass

        model.astream = slow_stream
        with pytest.raises(LlmServiceError, match="zaman aşımı"):
            async for _ in service.stream_answer(system_prompt="s", user_prompt="u"):
                pass
