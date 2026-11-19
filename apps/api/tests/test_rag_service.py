from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import (
    NO_RELEVANT_SOURCE_ANSWER,
    HistoryMessage,
    LlmServiceError,
    RetrievedChunk,
    answer_question,
    apply_citations,
    build_user_prompt,
    rewrite_question,
)
from app.services.rag_service import (
    HISTORY_CONTENT_CHARS,
    HISTORY_MESSAGE_LIMIT,
    build_rewrite_prompt,
)


def build_source() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="policy.pdf",
        page_number=2,
        content="Yıllık izin talebi sistem üzerinden oluşturulur.",
        similarity=0.82,
    )


def test_build_user_prompt_labels_untrusted_sources() -> None:
    prompt = build_user_prompt(
        question="Yıllık izin nasıl alınır?",
        sources=[build_source()],
    )

    assert "Soru:\nYıllık izin nasıl alınır?" in prompt
    assert "[Kaynak 1]" in prompt
    assert "Doküman: policy.pdf" in prompt
    assert "Sayfa: 2" in prompt
    assert "Yıllık izin talebi" in prompt


@pytest.mark.asyncio
async def test_answer_question_retrieves_sources_and_calls_llm() -> None:
    organization_id = uuid4()
    source = build_source()
    session = AsyncMock(spec=AsyncSession)
    embedding_service = MagicMock()
    llm_service = MagicMock()

    async def generate_answer(**_: object) -> str:
        # Both retrieval transactions must be closed before the model runs.
        assert session.commit.await_count == 2
        return "İzin talebi sistemden oluşturulur. [Kaynak 1]"

    llm_service.generate_answer = AsyncMock(side_effect=generate_answer)

    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=([], "Yıllık izin nasıl alınır?")),
        ),
        patch(
            "app.services.rag_service.search_relevant_chunks",
            new=AsyncMock(return_value=[source]),
        ) as search_mock,
    ):
        result = await answer_question(
            organization_id=organization_id,
            question="Yıllık izin nasıl alınır?",
            session=session,
            embedding_service=embedding_service,
            llm_service=llm_service,
            limit=4,
            minimum_similarity=0.4,
        )

    assert result.answer == "İzin talebi sistemden oluşturulur. [Kaynak 1]"
    assert result.sources == [source]
    search_mock.assert_awaited_once_with(
        organization_id=organization_id,
        query="Yıllık izin nasıl alınır?",
        session=session,
        embedding_service=embedding_service,
        limit=4,
        minimum_similarity=0.4,
        folder_ids=[],
        document_ids=None,
    )
    llm_service.generate_answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_answer_question_skips_llm_when_no_source_exists() -> None:
    llm_service = MagicMock()
    llm_service.generate_answer = AsyncMock()

    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=([], "Bilinmeyen soru")),
        ),
        patch(
            "app.services.rag_service.search_relevant_chunks",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = await answer_question(
            organization_id=uuid4(),
            question="Bilinmeyen soru",
            session=AsyncMock(spec=AsyncSession),
            embedding_service=MagicMock(),
            llm_service=llm_service,
        )

    assert result.answer == NO_RELEVANT_SOURCE_ANSWER
    assert result.sources == []
    llm_service.generate_answer.assert_not_awaited()


@pytest.mark.parametrize(
    ("answer", "expected_answer", "expected_source_indexes"),
    [
        ("A [Kaynak 1].", "A [Kaynak 1].", [0]),
        # Renumbered by first citation so the UI list starts at 1 and has no gaps.
        ("A [Kaynak 3]. B [Kaynak 1].", "A [Kaynak 1]. B [Kaynak 2].", [2, 0]),
        ("A [Kaynak 9].", "A.", []),
        ("A [Kaynak 0].", "A.", []),
        ("A [Kaynak 1] ve B [Kaynak 7].", "A [Kaynak 1] ve B.", [0]),
        ("A [Kaynak 1, 3].", "A [Kaynak 1][Kaynak 2].", [0, 2]),
        ("A [Kaynak 2-3].", "A [Kaynak 1][Kaynak 2].", [1, 2]),
        ("A [Kaynaklar: 1 ve 3].", "A [Kaynak 1][Kaynak 2].", [0, 2]),
        ("A [kaynak 2].", "A [Kaynak 1].", [1]),
        # A page number next to the source must not be read as another source.
        ("A [Kaynak 2, s. 3].", "A [Kaynak 1].", [1]),
        ("A [Kaynak 2, Sayfa 1].", "A [Kaynak 1].", [1]),
        ("A [Kaynak 1-100].", "A [Kaynak 1].", [0]),
        ("Kaynaklarda bu bilgi yok.", "Kaynaklarda bu bilgi yok.", []),
    ],
)
def test_apply_citations(
    answer: str,
    expected_answer: str,
    expected_source_indexes: list[int],
) -> None:
    sources = [build_source() for _ in range(3)]

    cleaned_answer, cited_sources = apply_citations(answer, sources)

    assert cleaned_answer == expected_answer
    assert cited_sources == [sources[index] for index in expected_source_indexes]


@pytest.mark.asyncio
async def test_rewrite_question_skips_llm_without_history() -> None:
    llm_service = MagicMock()
    llm_service.generate_answer = AsyncMock()

    result = await rewrite_question(question="Soru?", history=[], llm_service=llm_service)

    assert result == "Soru?"
    llm_service.generate_answer.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_output", "expected"),
    [
        ("Tanpınar'ın başka eseri var mı?", "Tanpınar'ın başka eseri var mı?"),
        (
            (
                '<think>düşünce</think>\nYeniden yazılmış soru: "Tanpınar\'ın başka eseri var mı?"\n'
                "Açıklama: geçmişten alındı."
            ),
            "Tanpınar'ın başka eseri var mı?",
        ),
        ("   \n  ", "Onun başka eseri var mı?"),
        ("a" * 501, "Onun başka eseri var mı?"),
    ],
)
async def test_rewrite_question_cleans_output_and_falls_back(
    model_output: str,
    expected: str,
) -> None:
    llm_service = MagicMock()
    llm_service.generate_answer = AsyncMock(return_value=model_output)

    result = await rewrite_question(
        question="Onun başka eseri var mı?",
        history=[HistoryMessage(role="user", content="Huzur'un yazarı kim?")],
        llm_service=llm_service,
    )

    assert result == expected


@pytest.mark.asyncio
async def test_rewrite_question_propagates_llm_errors() -> None:
    llm_service = MagicMock()
    llm_service.generate_answer = AsyncMock(side_effect=LlmServiceError("down"))

    with pytest.raises(LlmServiceError):
        await rewrite_question(
            question="Peki?",
            history=[HistoryMessage(role="user", content="Soru")],
            llm_service=llm_service,
        )


def test_build_rewrite_prompt_keeps_recent_history_without_old_citations() -> None:
    history = [HistoryMessage(role="user", content=f"eski {index}") for index in range(6)] + [
        HistoryMessage(role="user", content="Huzur'un yazarı kim?"),
        HistoryMessage(role="assistant", content="Tanpınar [Kaynak 3]. " + "x" * 2000),
    ]

    prompt = build_rewrite_prompt(question="Onun başka eseri?", history=history)

    assert "eski 0" not in prompt
    assert "eski 1" not in prompt
    assert "Kullanıcı: Huzur'un yazarı kim?" in prompt
    assert "[Kaynak 3]" not in prompt
    assert "x" * HISTORY_CONTENT_CHARS not in prompt
    assert prompt.endswith("Son soru:\nOnun başka eseri?\n\nYeniden yazılmış soru:")
    assert len(history) > HISTORY_MESSAGE_LIMIT


@pytest.mark.asyncio
async def test_answer_question_uses_rewritten_question_for_search_and_cites() -> None:
    sources = [build_source(), build_source()]
    llm_service = MagicMock()
    llm_service.generate_answer = AsyncMock(
        side_effect=[
            "Ahmet Hamdi Tanpınar'ın başka eserleri neler?",
            "Beş Şehir de onundur [Kaynak 2].",
        ]
    )
    history = [
        HistoryMessage(role="user", content="Huzur'un yazarı kim?"),
        HistoryMessage(role="assistant", content="Ahmet Hamdi Tanpınar [Kaynak 1]."),
    ]

    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=([], "Onun başka eseri var mı?")),
        ),
        patch(
            "app.services.rag_service.search_relevant_chunks",
            new=AsyncMock(return_value=sources),
        ) as search_mock,
    ):
        result = await answer_question(
            organization_id=uuid4(),
            question="@Edebiyat Onun başka eseri var mı?",
            session=AsyncMock(spec=AsyncSession),
            embedding_service=MagicMock(),
            llm_service=llm_service,
            history=history,
        )

    assert search_mock.await_args.kwargs["query"] == (
        "Ahmet Hamdi Tanpınar'ın başka eserleri neler?"
    )
    # The rewrite sees the question without the folder mention.
    rewrite_prompt = llm_service.generate_answer.await_args_list[0].kwargs["user_prompt"]
    assert "Son soru:\nOnun başka eseri var mı?" in rewrite_prompt
    answer_prompt = llm_service.generate_answer.await_args_list[1].kwargs["user_prompt"]
    assert "Soru:\n@Edebiyat Onun başka eseri var mı?" in answer_prompt
    assert (
        "Konuşma bağlamına göre sorunun açık hali:\nAhmet Hamdi Tanpınar'ın başka eserleri neler?"
    ) in answer_prompt
    assert result.answer == "Beş Şehir de onundur [Kaynak 1]."
    assert result.sources == [sources[1]]


@pytest.mark.asyncio
async def test_answer_question_with_only_invalid_citations_returns_no_answer() -> None:
    llm_service = MagicMock()
    llm_service.generate_answer = AsyncMock(return_value="[Kaynak 7]")

    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=([], "Soru?")),
        ),
        patch(
            "app.services.rag_service.search_relevant_chunks",
            new=AsyncMock(return_value=[build_source()]),
        ),
    ):
        result = await answer_question(
            organization_id=uuid4(),
            question="Soru?",
            session=AsyncMock(spec=AsyncSession),
            embedding_service=MagicMock(),
            llm_service=llm_service,
        )

    assert result.answer == NO_RELEVANT_SOURCE_ANSWER
    assert result.sources == []
