from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.account import AccountStatus
from app.domain.posting import EntryDirection


class WalletCreateRequest(BaseModel):
    currency: str = Field(min_length=3, max_length=3)


class WalletUpdateRequest(BaseModel):
    # What the owner calls this wallet; null or blank removes the name.
    name: str | None = Field(max_length=40)


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # What the owner shares to receive money: 16 digits, FinCore's own.
    card_number: str
    currency: str
    status: AccountStatus
    # The owner's own label, if they gave one.
    name: str | None
    # Their main wallet: listed first and offered first when paying.
    is_primary: bool
    # Blocked by the owner: money can arrive but none can leave.
    blocked: bool
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
