import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthSession, Organization, OrganizationMembership, OrganizationRole, User

PBKDF2_ITERATIONS = 600_000
SESSION_LIFETIME = timedelta(hours=24)


class CredentialsError(Exception):
    pass


class RegistrationConflictError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class IssuedToken:
    value: str
    expires_at: datetime


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(salt), int(iterations)
        )
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_token(*, user: User, session: AsyncSession) -> IssuedToken:
    value = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + SESSION_LIFETIME
    session.add(AuthSession(user_id=user.id, token_hash=_token_hash(value), expires_at=expires_at))
    await session.flush()
    return IssuedToken(value=value, expires_at=expires_at)


async def register_user_and_organization(
    *,
    email: str,
    password: str,
    organization_name: str,
    organization_slug: str,
    session: AsyncSession,
) -> tuple[User, Organization, IssuedToken]:
    try:
        user = User(email=email, password_hash=hash_password(password))
        organization = Organization(name=organization_name, slug=organization_slug)
        session.add_all([user, organization])
        await session.flush()
        session.add(
            OrganizationMembership(
                organization_id=organization.id, user_id=user.id, role=OrganizationRole.OWNER
            )
        )
        token = await issue_token(user=user, session=session)
        await session.commit()
        await session.refresh(user)
        await session.refresh(organization)
    except IntegrityError as error:
        await session.rollback()
        raise RegistrationConflictError("E-posta veya organizasyon adresi kullanımda.") from error
    except SQLAlchemyError:
        await session.rollback()
        raise
    return user, organization, token


async def authenticate_user(
    *, email: str, password: str, session: AsyncSession
) -> tuple[User, IssuedToken]:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        raise CredentialsError("E-posta veya parola hatalı.")
    try:
        token = await issue_token(user=user, session=session)
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise
    return user, token


async def get_user_by_token(*, token: str, session: AsyncSession) -> User | None:
    statement = (
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == _token_hash(token), AuthSession.expires_at > datetime.now(UTC)
        )
    )
    return await session.scalar(statement)


async def list_user_organization_ids(*, user_id: UUID, session: AsyncSession) -> list[UUID]:
    result = await session.scalars(
        select(OrganizationMembership.organization_id).where(
            OrganizationMembership.user_id == user_id
        )
    )
    return list(result.all())
