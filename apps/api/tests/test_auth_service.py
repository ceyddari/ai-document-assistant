from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.auth_service import (
    CredentialsError,
    authenticate_user,
    hash_password,
    verify_password,
)


def test_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("correct-horse-battery")
    second = hash_password("correct-horse-battery")

    assert first != second
    assert verify_password("correct-horse-battery", first)
    assert not verify_password("wrong-password", first)


@pytest.mark.asyncio
async def test_authenticate_user_rejects_invalid_password() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = User(
        id=uuid4(), email="user@example.com", password_hash=hash_password("valid-password-123")
    )

    with pytest.raises(CredentialsError):
        await authenticate_user(
            email="user@example.com", password="invalid-password", session=session
        )

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticate_user_issues_hashed_session_token() -> None:
    session = AsyncMock(spec=AsyncSession)
    user = User(
        id=uuid4(), email="user@example.com", password_hash=hash_password("valid-password-123")
    )
    session.scalar.return_value = user
    session.add = MagicMock()

    result_user, token = await authenticate_user(
        email="user@example.com", password="valid-password-123", session=session
    )

    stored_session = session.add.call_args.args[0]
    assert result_user is user
    assert token.value not in stored_session.token_hash
    assert len(stored_session.token_hash) == 64
    session.commit.assert_awaited_once()
