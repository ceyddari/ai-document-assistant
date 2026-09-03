# This file allows us to reuse FastAPI dependency injection definitions.

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session

DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db_session),
]

AppSettings = Annotated[
    Settings,
    Depends(get_settings),
]
