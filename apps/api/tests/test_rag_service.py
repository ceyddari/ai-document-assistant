from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import (
    NO_RELEVANT_SOURCE_ANSWER,
    RetrievedChunk,
    answer_question,
    build_user_prompt,
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
    llm_service.generate_answer = AsyncMock(
        return_value="İzin talebi sistemden oluşturulur. [Kaynak 1]"
    )

    with patch(
        "app.services.rag_service.search_relevant_chunks",
        new=AsyncMock(return_value=[source]),
    ) as search_mock:
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
    )
    llm_service.generate_answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_answer_question_skips_llm_when_no_source_exists() -> None:
    llm_service = MagicMock()
    llm_service.generate_answer = AsyncMock()

    with patch(
        "app.services.rag_service.search_relevant_chunks",
        new=AsyncMock(return_value=[]),
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
