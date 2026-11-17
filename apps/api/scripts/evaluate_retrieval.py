"""Retrieval kalitesini ölçer: hit@k ve MRR.

Repo kökünden çalıştırın (.env oradan okunur):
    python apps/api/scripts/evaluate_retrieval.py [vaka_dosyası] [--limit 5] [--no-rewrite]

Vaka dosyası (varsayılan storage/eval/retrieval_cases.json):
    {"organization_id": "...",
     "cases": [{"question": "...",
                "history": [{"role": "user", "content": "..."}],   (isteğe bağlı)
                "expected": [{"filename": "x.pdf", "pages": [3, 4]}]}]}

Sonuçlardan biri beklenen dosya + sayfalardan birine denk gelirse vaka bulunmuş sayılır.
`expected` boş olan vakalar negatiftir: skora girmez, kaç kaynak döndüğü raporlanır.
Vakalar özel doküman içeriği taşıdığı için dosyayı gitignore'daki storage/ altında tutun.
"""

import argparse
import asyncio
import json
import sys
import time
import unicodedata
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services import (
    EmbeddingService,
    HistoryMessage,
    LlmService,
    RetrievedChunk,
    rewrite_question,
    search_relevant_chunks,
)

DEFAULT_CASES_PATH = Path("storage/eval/retrieval_cases.json")
K_VALUES = (1, 3, 5)


def _nfc(text: str) -> str:
    # Uploaded filenames can be NFD (e.g. from macOS); "Ü" must equal "U" + U+0308.
    return unicodedata.normalize("NFC", text)


def first_hit_rank(results: list[RetrievedChunk], expected: list[dict]) -> int | None:
    for rank, result in enumerate(results, start=1):
        if any(
            _nfc(result.filename) == _nfc(item["filename"]) and result.page_number in item["pages"]
            for item in expected
        ):
            return rank

    return None


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", nargs="?", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--no-rewrite", action="store_true", help="Takip sorularını yazmadan ara.")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page.

    data = json.loads(args.cases.read_text(encoding="utf-8"))
    organization_id = UUID(data["organization_id"])
    settings = get_settings()
    embedding_service = EmbeddingService(settings=settings)
    llm_service = LlmService(settings=settings)
    ranks: list[int | None] = []
    durations: list[float] = []

    async with get_session_factory()() as session:
        for case in data["cases"]:
            question = case["question"]
            history = [HistoryMessage(**message) for message in case.get("history", [])]
            started = time.perf_counter()
            query = (
                question
                if args.no_rewrite
                else await rewrite_question(
                    question=question, history=history, llm_service=llm_service
                )
            )
            results = await search_relevant_chunks(
                organization_id=organization_id,
                query=query,
                session=session,
                embedding_service=embedding_service,
                limit=args.limit,
                minimum_similarity=settings.retrieval_min_similarity,
            )
            durations.append(time.perf_counter() - started)
            rewritten = f"  -> {query}" if query != question else ""

            if not case["expected"]:
                print(f" NEG | {len(results)} kaynak | {question}")
                continue

            rank = first_hit_rank(results, case["expected"])
            ranks.append(rank)
            print(f"{f'#{rank}' if rank else 'MISS':>4} | {question}{rewritten}")

            if rank is None:
                for result in results[:3]:
                    print(
                        f"       {result.filename} s.{result.page_number} ({result.similarity:.2f})"
                    )

    if not ranks:
        print("Skorlanacak vaka yok.")
        return

    print()
    for k in K_VALUES:
        hits = sum(1 for rank in ranks if rank is not None and rank <= k)
        print(f"hit@{k}: {hits}/{len(ranks)} = {hits / len(ranks):.1%}")

    mrr = sum(1 / rank for rank in ranks if rank is not None) / len(ranks)
    print(f"MRR@{args.limit}: {mrr:.3f}")
    print(f"ortalama süre: {sum(durations) / len(durations) * 1000:.0f} ms")


if __name__ == "__main__":
    asyncio.run(main())
