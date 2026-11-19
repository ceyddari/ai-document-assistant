import json
from dataclasses import replace
from pathlib import Path
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
    stream_answer_question,
)
from app.services.pdf_parser import OutlineEntry
from app.services.rag_quality import (
    SUMMARY_QUESTION,
    ComparisonQueries,
    SectionSelection,
    VerificationResult,
)
from app.services.rag_service import (
    HISTORY_CONTENT_CHARS,
    HISTORY_MESSAGE_LIMIT,
    PARTIAL_ANSWER,
    SAMPLED_SUMMARY,
    RagOptions,
    _verify_answer,
    build_rewrite_prompt,
)
from app.services.reranker import rerank_chunks
from app.services.summary_service import SummaryPart


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
async def test_verifier_keeps_only_cited_claims_with_real_evidence_and_matching_numbers() -> None:
    leave_policy = replace(build_source(), content="Yıllık izin 10 iş günüdür.")
    request_policy = build_source()
    llm = MagicMock()
    llm.generate_structured = AsyncMock(
        return_value=VerificationResult.model_validate(
            {
                "status": "partial",
                "claims": [
                    {"id": 1, "evidence": [{"source": 1, "quote": "Yıllık izin 10 iş günüdür."}]},
                    {"id": 2, "evidence": [{"source": 2, "quote": "yöneticiye yazılır"}]},
                    {"id": 3, "evidence": [{"source": 2, "quote": request_policy.content}]},
                ],
            }
        )
    )

    answer = await _verify_answer(
        "İzin 15 iş günüdür. [Kaynak 1]\nTalep yöneticiye yazılır. [Kaynak 2]\n"
        "İzin talebi sistemden açılır. [Kaynak 2]\nHer başvuru onaylanır.",
        [leave_policy, request_policy],
        "İzin nasıl alınır ve kaç gün sürer?",
        llm,
    )

    assert answer.answer == f"İzin talebi sistemden açılır. [Kaynak 1]\n\n{PARTIAL_ANSWER}"
    assert answer.sources == [request_policy]
    payload = json.loads(llm.generate_structured.call_args.kwargs["user_prompt"])
    assert payload["question"] == "İzin nasıl alınır ve kaç gün sürer?"
    assert [claim["id"] for claim in payload["claims"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_verified_stream_emits_only_the_grounded_final_answer() -> None:
    source = replace(build_source(), content="Erişim izinleri yöneticiler tarafından verilir.")
    llm = MagicMock()
    llm.generate_answer = AsyncMock(
        return_value="Erişim izinleri yöneticilerce verilir. [Kaynak 1]"
    )
    llm.generate_structured = AsyncMock(
        return_value=VerificationResult(status="insufficient", claims=[])
    )
    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions", new=AsyncMock(return_value=([], ""))
        ),
        patch(
            "app.services.rag_service.search_relevant_chunks", new=AsyncMock(return_value=[source])
        ),
    ):
        events = [
            item
            async for item in stream_answer_question(
                organization_id=uuid4(),
                question="Yıllık izin kaç gündür?",
                session=AsyncMock(spec=AsyncSession),
                embedding_service=MagicMock(),
                llm_service=llm,
                options=RagOptions(verify_citations=True),
            )
        ]

    assert len(events) == 1
    assert events[0].answer == NO_RELEVANT_SOURCE_ANSWER
    assert events[0].sources == []
    llm.stream_answer.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("draft_days", [10, 15])
async def test_adaptive_stream_uses_one_pass_for_clear_sources_and_checks_bad_numbers(
    draft_days: int,
) -> None:
    strong = replace(build_source(), content="Yıllık izin 10 iş günüdür.", similarity=0.72)
    similar_same_page = replace(strong, chunk_id=uuid4(), similarity=0.71)
    unrelated = replace(build_source(), similarity=0.48)
    draft = f"Yıllık izin {draft_days} iş günüdür. [Kaynak 1]"
    llm = MagicMock()

    async def stream(**_: object):
        yield draft

    llm.stream_answer = MagicMock(side_effect=stream)
    llm.generate_structured = AsyncMock(
        return_value=VerificationResult(status="insufficient", claims=[])
    )
    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions", new=AsyncMock(return_value=([], ""))
        ),
        patch(
            "app.services.rag_service.search_relevant_chunks",
            new=AsyncMock(
                return_value=[strong, similar_same_page, unrelated],
            ),
        ),
        patch("app.services.rag_service.rerank_chunks", new=AsyncMock()) as rerank,
    ):
        events = [
            item
            async for item in stream_answer_question(
                organization_id=uuid4(),
                question="Yıllık izin kaç gündür?",
                session=AsyncMock(spec=AsyncSession),
                embedding_service=MagicMock(),
                llm_service=llm,
                options=RagOptions(
                    reranker_directory=Path("models"), verify_citations=True, adaptive_quality=True
                ),
            )
        ]

    rerank.assert_not_awaited()
    assert events[0] == draft
    if draft_days == 10:
        llm.generate_structured.assert_not_awaited()
        assert events[-1].answer == draft
    else:
        llm.generate_structured.assert_awaited_once()
        assert events[-1].answer == NO_RELEVANT_SOURCE_ANSWER


@pytest.mark.asyncio
async def test_adaptive_stream_keeps_deep_checks_for_competing_pages() -> None:
    candidates = [replace(build_source(), similarity=score) for score in (0.61, 0.60)]
    llm = MagicMock()
    llm.generate_answer = AsyncMock(return_value="İzin talebi sistemden açılır. [Kaynak 1]")
    llm.generate_structured = AsyncMock(
        return_value=VerificationResult(status="insufficient", claims=[])
    )
    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions", new=AsyncMock(return_value=([], ""))
        ),
        patch(
            "app.services.rag_service.search_relevant_chunks",
            new=AsyncMock(return_value=candidates),
        ),
        patch(
            "app.services.rag_service.rerank_chunks", new=AsyncMock(return_value=candidates)
        ) as rerank,
    ):
        events = [
            item
            async for item in stream_answer_question(
                organization_id=uuid4(),
                question="Yıllık izin nasıl alınır?",
                session=AsyncMock(spec=AsyncSession),
                embedding_service=MagicMock(),
                llm_service=llm,
                options=RagOptions(
                    reranker_directory=Path("models"), verify_citations=True, adaptive_quality=True
                ),
            )
        ]

    rerank.assert_awaited_once()
    llm.generate_structured.assert_awaited_once()
    llm.stream_answer.assert_not_called()
    assert len(events) == 1 and events[0].answer == NO_RELEVANT_SOURCE_ANSWER


@pytest.mark.asyncio
@pytest.mark.parametrize("adaptive_quality", [False, True])
async def test_comparison_searches_each_side_with_original_document_and_folder_scope(
    adaptive_quality: bool,
) -> None:
    documents, folders = [uuid4(), uuid4()], [uuid4()]
    source_a, source_b, distractor = build_source(), build_source(), build_source()
    llm = MagicMock()
    llm.generate_structured = AsyncMock(
        return_value=ComparisonQueries(queries=["2024 limiti", "2025 limiti"])
    )
    llm.generate_answer = AsyncMock(return_value="Limitler farklıdır. [Kaynak 1][Kaynak 2]")
    question = "2024 ve 2025 limitlerini karşılaştır."

    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=(folders, question)),
        ),
        patch(
            "app.services.rag_service.search_relevant_chunks",
            new=AsyncMock(
                side_effect=[[source_a, distractor], [source_b]],
            ),
        ) as search,
    ):
        answer = await answer_question(
            organization_id=uuid4(),
            question=question,
            session=AsyncMock(spec=AsyncSession),
            embedding_service=MagicMock(),
            llm_service=llm,
            document_ids=documents,
            limit=2,
            options=RagOptions(complex_questions=True, adaptive_quality=adaptive_quality),
        )

    assert answer.sources == [source_a, source_b]
    assert [call.kwargs["query"] for call in search.await_args_list] == [
        "2024 limiti",
        "2025 limiti",
    ]
    assert all(call.kwargs["folder_ids"] == folders for call in search.await_args_list)
    assert all(call.kwargs["document_ids"] == documents for call in search.await_args_list)
    assert llm.generate_answer.call_args.kwargs.get("reasoning", False) is not adaptive_quality


@pytest.mark.asyncio
async def test_document_summary_uses_ordered_sections_and_reports_sampling() -> None:
    document_id, folder_id = uuid4(), uuid4()
    sources = [
        replace(build_source(), document_id=document_id, page_number=index) for index in range(1, 9)
    ]
    llm = MagicMock()
    llm.generate_structured = AsyncMock(return_value=SectionSelection(sources=[2]))
    llm.generate_answer = AsyncMock(return_value="Özet. [Kaynak 1][Kaynak 2]")
    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=([folder_id], "Özetle")),
        ),
        patch(
            "app.services.rag_service.read_top_summaries",
            new=AsyncMock(return_value=([], False)),
        ),
        patch(
            "app.services.rag_service.read_summary_chunks",
            new=AsyncMock(return_value=(sources, True)),
        ) as read,
        patch("app.services.rag_service.search_relevant_chunks", new=AsyncMock()) as search,
    ):
        answer = await answer_question(
            organization_id=uuid4(),
            question="@Belgeler Özetle",
            session=AsyncMock(spec=AsyncSession),
            embedding_service=MagicMock(),
            llm_service=llm,
            document_ids=[document_id],
            options=RagOptions(complex_questions=True, verify_citations=True),
        )

    assert [source.page_number for source in answer.sources] == [2, 8]
    assert answer.answer.endswith(SAMPLED_SUMMARY)
    # Summaries skip claim verification, so only section selection used structured output.
    assert all(
        call.kwargs["schema"] is SectionSelection for call in llm.generate_structured.call_args_list
    )
    assert read.call_args.kwargs["folder_ids"] == [folder_id]
    assert read.call_args.kwargs["document_ids"] == [document_id]
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_reranker_preserves_ties_and_falls_back_when_inference_fails() -> None:
    sources = [build_source() for _ in range(3)]
    directory = Path("models")
    with patch("app.services.reranker._score", return_value=[0.2, 0.8, 0.8]):
        ranked = await rerank_chunks(model_directory=directory, query="izin", candidates=sources)
    assert ranked == [sources[1], sources[2], sources[0]]

    with patch("app.services.reranker._score", side_effect=ValueError):
        ranked = await rerank_chunks(model_directory=directory, query="izin", candidates=sources)
    assert ranked == sources


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


@pytest.mark.parametrize(
    "question",
    ["bu dokümanın genel başlıkları nelerdir", "ana konular neler", "bu belge ne hakkında"],
)
def test_overview_questions_use_summary_path(question: str) -> None:
    assert SUMMARY_QUESTION.search(question)


def test_specific_questions_do_not_use_summary_path() -> None:
    assert not SUMMARY_QUESTION.search("yıllık izin kaç gün")


@pytest.mark.asyncio
async def test_heading_question_answers_from_pdf_outline_without_llm() -> None:
    llm = MagicMock()
    llm.generate_answer = AsyncMock()
    outline = [OutlineEntry(1, "Giriş", 1), OutlineEntry(2, "Amaç", 2)]
    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=([], "başlıklar neler")),
        ),
        patch(
            "app.services.rag_service.read_document_files",
            new=AsyncMock(return_value=[("rapor.pdf", "/app/storage/x.pdf")]),
        ),
        patch("app.services.rag_service.parse_outline", return_value=outline),
    ):
        answer = await answer_question(
            organization_id=uuid4(),
            question="bu dokümanın genel başlıkları nelerdir",
            session=AsyncMock(spec=AsyncSession),
            embedding_service=MagicMock(),
            llm_service=llm,
            document_ids=[uuid4()],
            options=RagOptions(complex_questions=True),
        )

    assert answer.answer.endswith("- Giriş (s. 1)\n  - Amaç (s. 2)")
    llm.generate_answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_heading_question_without_outline_falls_back_to_summary() -> None:
    document_id = uuid4()
    llm = MagicMock()
    llm.generate_answer = AsyncMock(return_value="Başlıklar. [Kaynak 1]")
    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=([], "başlıkları nelerdir")),
        ),
        patch(
            "app.services.rag_service.read_document_files",
            new=AsyncMock(return_value=[("rapor.pdf", "/app/storage/x.pdf")]),
        ),
        patch("app.services.rag_service.parse_outline", return_value=[]),
        patch("app.services.rag_service.read_contents_chunks", new=AsyncMock(return_value=[])),
        patch(
            "app.services.rag_service.read_top_summaries",
            new=AsyncMock(return_value=([], False)),
        ),
        patch(
            "app.services.rag_service.read_summary_chunks",
            new=AsyncMock(return_value=([replace(build_source(), document_id=document_id)], False)),
        ),
    ):
        answer = await answer_question(
            organization_id=uuid4(),
            question="bu dokümanın genel başlıkları nelerdir",
            session=AsyncMock(spec=AsyncSession),
            embedding_service=MagicMock(),
            llm_service=llm,
            document_ids=[document_id],
            options=RagOptions(complex_questions=True),
        )

    assert answer.answer == "Başlıklar. [Kaynak 1]"
    llm.generate_answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_heading_question_without_outline_uses_printed_contents_page() -> None:
    contents = replace(build_source(), page_number=5, content="İÇİNDEKİLER 1. BÖLÜM Giriş ... 9")
    llm = MagicMock()
    llm.generate_answer = AsyncMock(return_value="- 1. Bölüm: Giriş (s. 9) [Kaynak 1]")
    llm.generate_structured = AsyncMock()
    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=([], "başlıkları nelerdir")),
        ),
        patch(
            "app.services.rag_service.read_document_files",
            new=AsyncMock(return_value=[("kitap.pdf", "/app/storage/x.pdf")]),
        ),
        patch("app.services.rag_service.parse_outline", return_value=[]),
        patch(
            "app.services.rag_service.read_contents_chunks",
            new=AsyncMock(return_value=[contents]),
        ),
        patch("app.services.rag_service.read_summary_chunks", new=AsyncMock()) as summary,
    ):
        answer = await answer_question(
            organization_id=uuid4(),
            question="bu dokümanın genel başlıkları nelerdir",
            session=AsyncMock(spec=AsyncSession),
            embedding_service=MagicMock(),
            llm_service=llm,
            document_ids=[contents.document_id],
            options=RagOptions(complex_questions=True, verify_citations=True),
        )

    assert answer.sources == [contents]
    assert "İÇİNDEKİLER" in llm.generate_answer.call_args.kwargs["user_prompt"]
    llm.generate_structured.assert_not_awaited()
    summary.assert_not_awaited()


@pytest.mark.asyncio
async def test_summary_uses_stored_section_summaries_covering_every_page() -> None:
    document_id = uuid4()
    parts = [
        SummaryPart(document_id, "kitap.pdf", uuid4(), 1, 40, "- Orkestrasyon"),
        SummaryPart(document_id, "kitap.pdf", uuid4(), 41, 135, "- Siber tehditler"),
    ]
    llm = MagicMock()
    llm.generate_answer = AsyncMock(return_value="Giriş [Kaynak 1]\nTehditler [Kaynak 2]")
    llm.generate_structured = AsyncMock()
    with (
        patch(
            "app.services.rag_service.resolve_folder_mentions",
            new=AsyncMock(return_value=([], "Özetle")),
        ),
        patch(
            "app.services.rag_service.read_top_summaries",
            new=AsyncMock(return_value=(parts, True)),
        ),
        patch("app.services.rag_service.read_summary_chunks", new=AsyncMock()) as sampled,
    ):
        answer = await answer_question(
            organization_id=uuid4(),
            question="bu dokümanı özetle",
            session=AsyncMock(spec=AsyncSession),
            embedding_service=MagicMock(),
            llm_service=llm,
            document_ids=[document_id],
            options=RagOptions(complex_questions=True, verify_citations=True),
        )

    assert [source.page_number for source in answer.sources] == [1, 41]
    assert "Sayfa 41-135 özeti" in llm.generate_answer.call_args.kwargs["user_prompt"]
    assert not answer.answer.endswith(SAMPLED_SUMMARY)
    sampled.assert_not_awaited()
    llm.generate_structured.assert_not_awaited()
