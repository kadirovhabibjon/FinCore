from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.account import AccountStatus
from app.domain.posting import EntryDirection


class WalletCreateRequest(BaseModel):
    currency: str = Field(min_length=3, max_length=3)


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    currency: str
    status: AccountStatus
    created_at: datetime
    balance_minor: int
    held_minor: int


class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    posting_id: UUID
    direction: EntryDirection
    amount_minor: int
    currency: str
    created_at: datetime
