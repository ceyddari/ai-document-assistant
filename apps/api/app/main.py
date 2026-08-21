from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session

app = FastAPI(
    title="AI Document Assistant API",
    description="Şirket içi dokümanlar üzerinde kaynaklı soru-cevap API'si",
    version="0.1.0",
)


DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


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
