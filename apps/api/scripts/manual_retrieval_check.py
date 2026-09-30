import asyncio
from uuid import UUID

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services import EmbeddingService, search_relevant_chunks

ORGANIZATION_ID = UUID("bee5b28d-6149-4548-8f32-f44a79d6918a")
QUERY = "Sürpriz Kasa projesinin mimarisi nasıldır?"


async def main() -> None:
    settings = get_settings()
    session_factory = get_session_factory()
    embedding_service = EmbeddingService(settings=settings)

    async with session_factory() as session:
        results = await search_relevant_chunks(
            organization_id=ORGANIZATION_ID,
            query=QUERY,
            session=session,
            embedding_service=embedding_service,
            limit=5,
        )

    if not results:
        print("İlgili chunk bulunamadı.")
        return

    for index, result in enumerate(results, start=1):
        print(f"\n--- Sonuç {index} ---")
        print(f"Doküman: {result.filename}")
        print(f"Doküman ID: {result.document_id}")
        print(f"Chunk ID: {result.chunk_id}")
        print(f"Sayfa: {result.page_number}")
        print(f"Benzerlik: {result.similarity:.4f}")
        print(f"İçerik: {result.content}")


if __name__ == "__main__":
    asyncio.run(main())
