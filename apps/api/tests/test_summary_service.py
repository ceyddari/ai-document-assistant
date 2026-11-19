from itertools import pairwise
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.summary_service import (
    SUMMARY_MAX_CHARS,
    TOP_LEVEL_CHARS,
    SummaryPart,
    build_summary_levels,
    fit_to_prompt,
    group_parts,
)


def make_parts(count: int, chars: int, document_id=None) -> list[SummaryPart]:
    document_id = document_id or uuid4()
    return [
        SummaryPart(document_id, "a.pdf", uuid4(), page, page, "x" * chars)
        for page in range(1, count + 1)
    ]


def fake_llm(summary_chars: int = 800) -> MagicMock:
    llm = MagicMock()
    llm.generate_answer = AsyncMock(return_value="<think>.</think>" + "ö" * summary_chars)
    return llm


def test_group_parts_respects_size_and_never_mixes_documents() -> None:
    first, second = make_parts(5, 1000), make_parts(2, 1000)
    groups = group_parts(first + second, 3000)
    assert [len(group) for group in groups] == [3, 2, 2]
    assert all(len({part.document_id for part in group}) == 1 for group in groups)


@pytest.mark.asyncio
async def test_levels_cover_all_pages_and_top_level_fits_one_prompt() -> None:
    # About a 135-page book: 400 chunks of 1000 characters.
    chunks = make_parts(400, 1000)
    llm = fake_llm()

    levels = await build_summary_levels(chunks, llm)

    top = levels[-1]
    assert len(levels) >= 2
    assert sum(len(part.content) for part in top) <= TOP_LEVEL_CHARS
    assert (top[0].start_page, top[-1].end_page) == (1, 400)
    # Every level covers every page, in order, without gaps.
    for parts in levels:
        assert all(a.end_page + 1 == b.start_page for a, b in pairwise(parts))
    assert "<think>" not in top[0].content
    assert len(top[0].content) <= SUMMARY_MAX_CHARS


@pytest.mark.asyncio
async def test_fit_to_prompt_keeps_small_scopes_and_samples_when_documents_are_too_many() -> None:
    small = make_parts(3, 500)
    llm = fake_llm()
    assert await fit_to_prompt(small, llm) == (small, False)
    llm.generate_answer.assert_not_awaited()

    many = [part for _ in range(20) for part in make_parts(1, SUMMARY_MAX_CHARS)]
    kept, sampled = await fit_to_prompt(many, llm)
    assert sampled
    assert sum(len(part.content) for part in kept) <= TOP_LEVEL_CHARS
