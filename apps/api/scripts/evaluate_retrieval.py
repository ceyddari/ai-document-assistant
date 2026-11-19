"""Kaynak bulma, atıf ve cevap kalitesini ölçer.

Repo kökünden çalıştırın (.env oradan okunur):
    python apps/api/scripts/evaluate_retrieval.py [vaka_dosyası] [--compare-reranker] [--answers]

Vaka dosyası (varsayılan storage/eval/retrieval_cases.json):
    {"organization_id": "...",
     "cases": [{"question": "...",
                "history": [{"role": "user", "content": "..."}],   (isteğe bağlı)
                "expected": [{"filename": "x.pdf", "pages": [3, 4]}],
                "required_sources": [{"filename": "y.pdf", "pages": [1]}],
                "answer_contains": ["beklenen ifade"]}]}

`required_sources` ve `answer_contains` isteğe bağlıdır. Her kaynak girdisi belge ve
alternatif sayfalar tanımlar. `required_sources` varsa grupların tamamı aranır.
`expected` ve `required_sources` boşsa vaka negatiftir.
Vakalar özel doküman içeriği taşıdığı için dosyayı gitignore'daki storage/ altında tutun.
"""

import argparse
import asyncio
import json
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services import (
    EmbeddingService,
    HistoryMessage,
    LlmService,
    RetrievedChunk,
    answer_question,
    rewrite_question,
    search_relevant_chunks,
)
from app.services.rag_service import NO_RELEVANT_SOURCE_ANSWER, RagOptions
from app.services.reranker import CANDIDATE_LIMIT, model_path, prepare_model, rerank_chunks

DEFAULT_CASES_PATH = Path("storage/eval/retrieval_cases.json")
K_VALUES = (1, 3, 5)


def _nfc(text: str) -> str:
    # Uploaded filenames can be NFD (e.g. from macOS); "Ü" must equal "U" + U+0308.
    return unicodedata.normalize("NFC", text)


def _answer_text(text: str) -> str:
    return " ".join(_nfc(text).replace("İ", "i").replace("I", "ı").casefold().split())


def first_hit_rank(results: list[RetrievedChunk], expected: list[dict]) -> int | None:
    for rank, result in enumerate(results, start=1):
        if any(
            _nfc(result.filename) == _nfc(item["filename"]) and result.page_number in item["pages"]
            for item in expected
        ):
            return rank

    return None


def covers_requirements(results: list[RetrievedChunk], required: list[dict]) -> bool:
    return all(first_hit_rank(results, [group]) is not None for group in required)


@dataclass
class Scorecard:
    ranks: list[int | None] = field(default_factory=list)
    durations: list[float] = field(default_factory=list)
    required_coverage: list[bool] = field(default_factory=list)
    negatives_with_sources: list[bool] = field(default_factory=list)
    answers_with_expected_citations: list[bool] = field(default_factory=list)
    answers_with_expected_text: list[bool] = field(default_factory=list)
    correct_abstentions: list[bool] = field(default_factory=list)

    def add_sources(
        self, results: list[RetrievedChunk], expected: list[dict], required: list[dict]
    ) -> str:
        if not expected:
            self.negatives_with_sources.append(bool(results))
            return f"NEG ({len(results)} kaynak)"
        rank = first_hit_rank(results, expected)
        self.ranks.append(rank)
        if required:
            self.required_coverage.append(covers_requirements(results, required))
        return f"#{rank}" if rank is not None else "MISS"

    def report(self, label: str, limit: int, *, answers: bool) -> None:
        print(f"\n{label}")
        if not answers and self.ranks:
            for k in K_VALUES:
                if k <= limit:
                    print_rate(f"hit@{k}", [rank is not None and rank <= k for rank in self.ranks])
            mrr = sum(1 / rank for rank in self.ranks if rank is not None) / len(self.ranks)
            print(f"MRR@{limit}: {mrr:.3f}")
        print_rate("tüm gerekli kaynaklar", self.required_coverage)
        print_rate("negatifte arama kaynağı döndü", self.negatives_with_sources)
        print_rate("beklenen sayfa atıfları", self.answers_with_expected_citations)
        print_rate("beklenen cevap ifadeleri", self.answers_with_expected_text)
        print_rate("negatifte doğru çekimserlik", self.correct_abstentions)
        if self.durations:
            ordered = sorted(self.durations)
            p95 = ordered[(95 * len(ordered) + 99) // 100 - 1]
            print(
                f"ortalama: {sum(ordered) / len(ordered) * 1000:.0f} ms, p95: {p95 * 1000:.0f} ms"
            )


def print_rate(label: str, outcomes: list[bool]) -> None:
    if outcomes:
        count = sum(outcomes)
        print(f"{label}: {count}/{len(outcomes)} = {count / len(outcomes):.1%}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", nargs="?", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--no-rewrite", action="store_true", help="Takip sorularını yazmadan ara.")
    parser.add_argument("--compare-reranker", action="store_true")
    parser.add_argument("--answers", action="store_true", help="Tam cevap ve atıf akışını ölç.")
    parser.add_argument(
        "--baseline", action="store_true", help="Cevap akışının eski ayarlarını kullan."
    )
    parser.add_argument(
        "--case", action="append", type=int, help="Yalnızca bu vaka numarasını çalıştır."
    )
    parser.add_argument(
        "--prepare-reranker", action="store_true", help="Yerel ONNX modelini indir."
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page.
    settings = get_settings()
    model_directory = model_path(settings.storage_directory)
    if args.prepare_reranker:
        prepare_model(model_directory)
        print(f"Reranker hazır: {model_directory}")
        return
    if not 1 <= args.limit <= 20:
        parser.error("--limit 1 ile 20 arasında olmalıdır.")
    if args.answers and args.compare_reranker:
        parser.error("--compare-reranker arama ölçümüne özeldir.")

    data = json.loads(args.cases.read_text(encoding="utf-8"))
    organization_id = UUID(data["organization_id"])
    embedding_service = EmbeddingService(settings=settings)
    llm_service = LlmService(settings=settings)
    baseline = Scorecard()
    reranked = Scorecard()
    rag_options = RagOptions() if args.baseline else RagOptions.from_settings(settings)
    if args.case and not all(1 <= number <= len(data["cases"]) for number in args.case):
        parser.error("Vaka numarası dosyada bulunamadı.")

    async with get_session_factory()() as session:
        for number, case in enumerate(data["cases"], start=1):
            if args.case and number not in args.case:
                continue
            question = case["question"]
            history = (
                []
                if args.no_rewrite
                else [HistoryMessage(**message) for message in case.get("history", [])]
            )
            required = case.get("required_sources", [])
            expected = case.get("expected") or required
            document_ids = [UUID(value) for value in case.get("document_ids", [])] or None
            started = time.perf_counter()
            if args.answers:
                answer = await answer_question(
                    organization_id=organization_id,
                    question=question,
                    history=history,
                    document_ids=document_ids,
                    session=session,
                    embedding_service=embedding_service,
                    llm_service=llm_service,
                    limit=args.limit,
                    minimum_similarity=settings.retrieval_min_similarity,
                    options=rag_options,
                )
                baseline.durations.append(time.perf_counter() - started)
                if expected:
                    passed = (
                        covers_requirements(answer.sources, required)
                        if required
                        else first_hit_rank(answer.sources, expected) is not None
                    )
                    baseline.answers_with_expected_citations.append(passed)
                    status = "ATIF OK" if passed else "ATIF EKSİK"
                else:
                    passed = answer.answer == NO_RELEVANT_SOURCE_ANSWER
                    baseline.correct_abstentions.append(passed)
                    status = "NEG OK" if passed else "NEG CEVAPLANDI"
                if phrases := case.get("answer_contains"):
                    baseline.answers_with_expected_text.append(
                        all(
                            _answer_text(phrase) in _answer_text(answer.answer)
                            for phrase in phrases
                        )
                    )
                print(f"{number:>3} | {status} | {question}\n      {answer.answer}", flush=True)
                for source in answer.sources:
                    print(f"      {source.filename} s.{source.page_number}", flush=True)
                continue

            query = await rewrite_question(
                question=question, history=history, llm_service=llm_service
            )
            rewrite_duration = time.perf_counter() - started
            results = await search_relevant_chunks(
                organization_id=organization_id,
                query=query,
                session=session,
                embedding_service=embedding_service,
                limit=args.limit,
                minimum_similarity=settings.retrieval_min_similarity,
                document_ids=document_ids,
            )
            await session.commit()
            baseline.durations.append(time.perf_counter() - started)
            status = baseline.add_sources(results, expected, required)
            if args.compare_reranker:
                started = time.perf_counter()
                candidates = await search_relevant_chunks(
                    organization_id=organization_id,
                    query=query,
                    session=session,
                    embedding_service=embedding_service,
                    limit=max(CANDIDATE_LIMIT, args.limit),
                    minimum_similarity=settings.retrieval_min_similarity,
                    document_ids=document_ids,
                )
                await session.commit()
                ordered = await rerank_chunks(
                    model_directory=model_directory, query=query, candidates=candidates, strict=True
                )
                reranked.durations.append(rewrite_duration + time.perf_counter() - started)
                status += " / " + reranked.add_sources(ordered[: args.limit], expected, required)
            print(f"{number:>3} | {status} | {question}", flush=True)

    baseline.report(
        "Cevap akışı" if args.answers else "Hibrit arama", args.limit, answers=args.answers
    )
    if args.compare_reranker:
        reranked.report("Hibrit arama + reranker", args.limit, answers=False)


if __name__ == "__main__":
    asyncio.run(main())
