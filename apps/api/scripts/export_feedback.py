"""Kullanıcı oylarını değerlendirme setine aday vaka olarak aktarır.

Repo kökünden çalıştırın:
    python apps/api/scripts/export_feedback.py [çıktı_dosyası]

👍 alan her cevap için bir vaka yazılır: soru, önceki mesajlar (history) ve cevabın atıf yaptığı
kaynakların dosya/sayfa bilgisi (expected). Biçim evaluate_retrieval.py ile aynıdır; gözden
geçirip retrieval_cases.json'a taşıyın. 👎 alan cevaplar "needs_review" altında listelenir:
beklenen sayfayı bir insanın belirlemesi gerekir.
Çıktı (varsayılan storage/eval/feedback_cases.json) özel içerik taşır; storage/ altında tutun.
"""

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models import Document, DocumentChunk, Message, MessageRole, MessageSource
from app.services.rag_service import HISTORY_MESSAGE_LIMIT

DEFAULT_OUTPUT_PATH = Path("storage/eval/feedback_cases.json")


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page.
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_PATH
    cases_by_organization: dict[str, list[dict]] = defaultdict(list)
    review_by_organization: dict[str, list[dict]] = defaultdict(list)

    async with get_session_factory()() as session:
        voted = (
            await session.scalars(
                select(Message)
                .where(Message.role == MessageRole.ASSISTANT, Message.feedback.is_not(None))
                .order_by(Message.created_at)
            )
        ).all()

        for answer in voted:
            earlier = (
                await session.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == answer.conversation_id,
                        Message.sequence < answer.sequence,
                    )
                    .order_by(Message.sequence.desc())
                    .limit(HISTORY_MESSAGE_LIMIT + 1)
                )
            ).all()[::-1]

            # The assistant message always follows its question; anything else is corrupt data.
            if not earlier or earlier[-1].role != MessageRole.USER:
                continue

            question, history = earlier[-1], earlier[:-1]
            organization = str(answer.organization_id)
            case = {
                "question": question.content,
                "history": [
                    {"role": message.role.value, "content": message.content} for message in history
                ],
            }

            if answer.feedback == -1:
                review_by_organization[organization].append({**case, "answer": answer.content})
                continue

            rows = (
                await session.execute(
                    select(Document.original_filename, DocumentChunk.page_number)
                    .join(DocumentChunk, DocumentChunk.document_id == Document.id)
                    .join(MessageSource, MessageSource.chunk_id == DocumentChunk.id)
                    .where(MessageSource.message_id == answer.id)
                    .order_by(MessageSource.position)
                )
            ).all()
            pages_by_file: dict[str, list[int]] = defaultdict(list)

            for filename, page_number in rows:
                if page_number not in pages_by_file[filename]:
                    pages_by_file[filename].append(page_number)

            # A helpful answer without sources ("not in the documents") is a negative case.
            case["expected"] = [
                {"filename": filename, "pages": pages} for filename, pages in pages_by_file.items()
            ]
            cases_by_organization[organization].append(case)

    organizations = sorted(set(cases_by_organization) | set(review_by_organization))
    output = [
        {
            "organization_id": organization,
            "cases": cases_by_organization[organization],
            "needs_review": review_by_organization[organization],
        }
        for organization in organizations
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    for item in output:
        print(
            f"{item['organization_id']}: {len(item['cases'])} aday vaka, "
            f"{len(item['needs_review'])} inceleme bekleyen"
        )
    print(f"Yazıldı: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
