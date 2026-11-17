"""Hazır dokümanların embedding'lerini mevcut chunk'lar üzerinden yeniden üretir.

Embedding girdisinin biçimi (build_embedding_text) değiştiğinde repo kökünden çalıştırın:
    python apps/api/scripts/reembed_documents.py

Chunk satırları silinmez, yalnızca embedding kolonu güncellenir; bu yüzden sayfa numaraları
ve konuşmalardaki kaynak kayıtları korunur. Her doküman ayrı transaction'dır: hata olursa o
doküman eski haliyle kalır, önceki dokümanlar güncellenmiş olur ve script yeniden çalıştırılabilir.
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import Document, DocumentChunk, DocumentStatus
from app.services import EmbeddingService
from app.services.document_processing_service import build_embedding_text


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page.
    embedding_service = EmbeddingService(settings=get_settings())

    async with get_session_factory()() as session:
        documents = (
            await session.scalars(
                select(Document)
                .where(Document.status == DocumentStatus.READY)
                .order_by(Document.created_at)
            )
        ).all()

        for index, document in enumerate(documents, start=1):
            chunks = (
                await session.scalars(
                    select(DocumentChunk)
                    .where(DocumentChunk.document_id == document.id)
                    .order_by(DocumentChunk.chunk_index)
                )
            ).all()

            try:
                embeddings = await embedding_service.embed_documents(
                    [
                        build_embedding_text(
                            filename=document.original_filename, content=chunk.content
                        )
                        for chunk in chunks
                    ]
                )

                for chunk, embedding in zip(chunks, embeddings, strict=True):
                    chunk.embedding = embedding

                await session.commit()
            except Exception:
                await session.rollback()
                print(f"Durdu: {document.original_filename} güncellenemedi; değişmeden kaldı.")
                raise

            print(f"[{index}/{len(documents)}] {document.original_filename}: {len(chunks)} chunk")


if __name__ == "__main__":
    asyncio.run(main())
