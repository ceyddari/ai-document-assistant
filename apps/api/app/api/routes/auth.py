from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import CurrentUser, DatabaseSession, bearer_scheme
from app.core.rate_limit import (
    RateLimiter,
    login_account_limiter,
    login_ip_limiter,
    register_limiter,
)
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth_service import (
    CredentialsError,
    RegistrationConflictError,
    authenticate_user,
    list_user_organization_ids,
    register_user_and_organization,
    revoke_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    # Behind a reverse proxy this is the proxy's address; configure the proxy headers
    # (e.g. uvicorn --proxy-headers) before relying on per-IP limits in production.
    return request.client.host if request.client else "unknown"


def _enforce(limiter: RateLimiter, key: str) -> None:
    retry_after = limiter.retry_after(key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Çok fazla deneme yaptınız. Lütfen biraz sonra tekrar deneyin.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest, http_request: Request, session: DatabaseSession
) -> TokenResponse:
    ip = _client_ip(http_request)
    _enforce(register_limiter, ip)
    register_limiter.record(ip)
    try:
        user, organization, token = await register_user_and_organization(
            email=request.email,
            password=request.password,
            organization_name=request.organization_name,
            organization_slug=request.organization_slug,
            session=session,
        )
    except RegistrationConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kayıt şu anda tamamlanamıyor.",
        ) from error
    return TokenResponse(
        access_token=token.value,
        expires_at=token.expires_at,
        user=UserResponse.model_validate(user),
        organization_id=organization.id,
        organization_ids=[organization.id],
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest, http_request: Request, session: DatabaseSession
) -> TokenResponse:
    ip = _client_ip(http_request)
    account_key = f"{ip}|{request.email}"
    _enforce(login_ip_limiter, ip)
    _enforce(login_account_limiter, account_key)
    try:
        user, token = await authenticate_user(
            email=request.email, password=request.password, session=session
        )
        organization_ids = await list_user_organization_ids(user_id=user.id, session=session)
    except CredentialsError as error:
        login_ip_limiter.record(ip)
        login_account_limiter.record(account_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Giriş şu anda tamamlanamıyor.",
        ) from error
    login_account_limiter.reset(account_key)
    return TokenResponse(
        access_token=token.value,
        expires_at=token.expires_at,
        user=UserResponse.model_validate(user),
        organization_ids=organization_ids,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    _: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: DatabaseSession,
) -> Response:
    # CurrentUser already proved the token is valid, so `credentials` is set here.
    if credentials is not None:
        try:
            await revoke_token(token=credentials.credentials, session=session)
        except SQLAlchemyError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Çıkış şu anda tamamlanamıyor.",
            ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
