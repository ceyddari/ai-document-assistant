from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DatabaseSession
from app.api.routes import documents_router

app = FastAPI(
    title="AI Document Assistant API",
    description="Şirket içi dokümanlar üzerinde kaynaklı soru-cevap API'si",
    version="0.1.0",
)

app.include_router(documents_router)


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
