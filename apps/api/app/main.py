from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DatabaseSession
from app.api.routes import (
    ai_router,
    ask_router,
    auth_router,
    conversations_router,
    documents_router,
    search_router,
)

app = FastAPI(
    title="AI Document Assistant API",
    description="Şirket içi dokümanlar üzerinde kaynaklı soru-cevap API'si",
    version="0.1.0",
)

app.include_router(documents_router)
app.include_router(auth_router)
app.include_router(search_router)
app.include_router(ask_router)
app.include_router(ai_router)
app.include_router(conversations_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness", tags=["system"])
async def readiness_check(session: DatabaseSession) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503,
            detail="Database is unavailable",
        ) from error

    return {"status": "ready"}
