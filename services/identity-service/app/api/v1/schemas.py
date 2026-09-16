from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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
        return value.strip()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    phone: str
    first_name: str
    last_name: str
    status: UserStatus
    created_at: datetime
