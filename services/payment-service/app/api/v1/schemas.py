import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.transfer import FraudDecision, Transfer, TransferStatus


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


class TransactionType(enum.StrEnum):
    """The kind of business operation a transaction summarizes (spec
    Section 20's API map). TRANSFER is the only kind that exists yet;
    PAYMENT joins this once payment-service grows a `POST /api/v1/payments`
    (Phase 5) — the unified list/detail endpoints exist now specifically
    so that addition doesn't change their shape.
    """

    TRANSFER = "TRANSFER"


class TransactionResponse(BaseModel):
    """A type-erased view over any business operation (currently just
    Transfer) for the user-facing history endpoints
    (`GET /api/v1/transactions[/{id}]`) — distinct from `TransferResponse`,
    which is transfer-specific and used by the transfer API itself.
    """

    id: UUID
    type: TransactionType
    reference: str
    status: str
    amount_minor: int
    currency: str
    description: str | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_transfer(cls, transfer: Transfer) -> "TransactionResponse":
        return cls(
            id=transfer.id,
            type=TransactionType.TRANSFER,
            reference=transfer.reference,
            status=transfer.status.value,
            amount_minor=transfer.amount_minor,
            currency=transfer.currency,
            description=transfer.description,
            created_at=transfer.created_at,
            completed_at=transfer.completed_at,
        )
