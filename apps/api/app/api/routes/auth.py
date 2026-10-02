from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import CurrentUser, DatabaseSession
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth_service import (
    CredentialsError,
    RegistrationConflictError,
    authenticate_user,
    list_user_organization_ids,
    register_user_and_organization,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, session: DatabaseSession) -> TokenResponse:
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
async def login(request: LoginRequest, session: DatabaseSession) -> TokenResponse:
    try:
        user, token = await authenticate_user(
            email=request.email, password=request.password, session=session
        )
        organization_ids = await list_user_organization_ids(user_id=user.id, session=session)
    except CredentialsError as error:
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
    return TokenResponse(
        access_token=token.value,
        expires_at=token.expires_at,
        user=UserResponse.model_validate(user),
        organization_ids=organization_ids,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
