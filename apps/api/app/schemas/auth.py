from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)]
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]


class RegisterRequest(BaseModel):
    email: Email
    password: Password
    organization_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]
    organization_slug: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=2,
            max_length=100,
            pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        ),
    ]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("Geçerli bir e-posta adresi girilmelidir.")
        return value.casefold()


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse
    organization_id: UUID | None = None
    organization_ids: list[UUID] = Field(default_factory=list)
