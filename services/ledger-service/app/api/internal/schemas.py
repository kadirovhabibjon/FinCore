from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.hold import HoldStatus
from app.domain.posting import EntryDirection, PostingType


class EntryRequest(BaseModel):
    account_id: UUID
    direction: EntryDirection
    amount_minor: int = Field(gt=0)


class CreatePostingRequest(BaseModel):
    source_service: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)
    type: PostingType
    currency: str = Field(min_length=3, max_length=3)
    entries: list[EntryRequest] = Field(min_length=2)


class PostingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_service: str
    source_id: str
    type: PostingType
    currency: str
    created_at: datetime


class CreateHoldRequest(BaseModel):
    source_service: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)
    account_id: UUID
    amount_minor: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    ttl_seconds: int = Field(default=900, gt=0)


class HoldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    amount_minor: int
    currency: str
    status: HoldStatus
    created_at: datetime
    expires_at: datetime
    resolved_at: datetime | None


class CaptureHoldRequest(BaseModel):
    source_service: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)
    amount_minor: int = Field(gt=0)
