# This file allows us to reuse FastAPI dependency injection definitions.

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models import OrganizationMembership, User
from app.services.auth_service import get_user_by_token

bearer_scheme = HTTPBearer(auto_error=False)

DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db_session),
]

AppSettings = Annotated[
    Settings,
    Depends(get_settings),
]


async def get_current_user(
    session: DatabaseSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    user = None
    if credentials is not None and credentials.scheme.casefold() == "bearer":
        user = await get_user_by_token(token=credentials.credentials, session=session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçerli kimlik doğrulama bilgisi gerekli.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_organization_member(
    organization_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
) -> OrganizationMembership:
    membership = await session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organizasyon bulunamadı."
        )
    return membership
