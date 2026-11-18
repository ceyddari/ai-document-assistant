import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DatabaseSession
from app.api.routes import (
    ai_router,
    ask_router,
    auth_router,
    conversations_router,
    documents_router,
    folders_router,
    search_router,
)
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services import fail_interrupted_documents

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Background processing dies with the process; without this, documents stay
    # "processing" forever and cannot be retried.
    try:
        async with get_session_factory()() as session:
            count = await fail_interrupted_documents(session=session)
        if count:
            logger.warning("Yarıda kalan %s doküman 'failed' olarak işaretlendi.", count)
    except (OSError, SQLAlchemyError):
        logger.exception("Yarıda kalan dokümanlar açılışta güncellenemedi.")
    yield


app = FastAPI(
    title="AI Document Assistant API",
    description="Yüklenen dokümanlar üzerinde kaynaklı soru-cevap API'si",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)
app.include_router(folders_router)
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
