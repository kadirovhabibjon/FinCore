from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.phone import normalize_phone
from app.domain.user import UserStatus


class RegisterRequest(BaseModel):
    email: EmailStr
    phone: str = Field(min_length=5, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        # EmailStr already validated the shape; normalize before it ever
        # reaches the uniqueness check or the database.
        return value.strip().lower()

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        # Stored in one canonical form, so it can later be used to sign in
        # however it's typed (app/core/phone.py).
        return normalize_phone(value)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    phone: str
    first_name: str
    last_name: str
    status: UserStatus
    created_at: datetime


class CurrentUserResponse(UserResponse):
    """`GET /users/me`: the caller's own profile plus their roles, so a
    client can decide what to show (e.g. the admin panel) without
    decoding the JWT itself. Server-side checks never rely on this."""

    roles: list[str]


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    last_used_at: datetime | None
    user_agent: str | None
    ip_address: str | None
    current: bool = False


class AdminUserResponse(UserResponse):
    roles: list[str]


class UserStatusUpdateRequest(BaseModel):
    status: UserStatus


class LoginRequest(BaseModel):
    """Sign in with email or phone number - exactly one - and password."""

    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value is not None else None

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> "LoginRequest":
        if (self.email is None) == (self.phone is None):
            raise ValueError("give either email or phone")
        return self


class PasswordResetRequest(BaseModel):
    """Whose password to reset: email or phone number, exactly one."""

    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=1, max_length=32)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value is not None else None

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> "PasswordResetRequest":
        if (self.email is None) == (self.phone is None):
            raise ValueError("give either email or phone")
        return self


class PasswordResetConfirmRequest(PasswordResetRequest):
    # The 6 digits from the email.
    code: str = Field(pattern=r"^[0-9]{6}$")
    # Same rules as RegisterRequest.password.
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    # null when the caller asked for cookie transport (ADR-0006): the
    # refresh token is then set as an httpOnly cookie and deliberately
    # kept out of anything JavaScript can read.
    refresh_token: str | None
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    # Same rules as RegisterRequest.password.
    new_password: str = Field(min_length=8, max_length=128)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)
