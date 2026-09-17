from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.transfer import FraudDecision, TransferStatus


class CreateTransferRequest(BaseModel):
    source_wallet_id: UUID
    destination_wallet_id: UUID
    # Decimal string at the API boundary, never a JSON number (ADR-0001).
    amount: str = Field(min_length=1, max_length=32)
    currency: str = Field(min_length=3, max_length=3)
    description: str | None = Field(default=None, max_length=255)


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    source_wallet_id: UUID
    destination_wallet_id: UUID
    amount_minor: int
    currency: str
    status: TransferStatus
    failure_reason: str | None
    fraud_decision: FraudDecision | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
