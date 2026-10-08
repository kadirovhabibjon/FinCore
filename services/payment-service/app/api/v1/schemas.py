import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.exchange import Exchange, ExchangeStatus
from app.domain.merchant import MerchantStatus
from app.domain.payment import Payment, PaymentStatus
from app.domain.refund import RefundStatus
from app.domain.transfer import FraudDecision, Transfer, TransferStatus
from app.services.reviews import ReviewDecision


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


class RecipientResponse(BaseModel):
    """Who a card number or phone number leads to, for the sender to confirm."""

    # What to send as `destination_wallet_id` when creating the transfer.
    wallet_id: UUID
    currency: str
    # First name and last initial, e.g. "Aziza K.".
    display_name: str
    # True when the card is one of the caller's own wallets.
    own: bool
    # The last four digits of the card the money would go to.
    card_last4: str | None = None


class RecentRecipientResponse(BaseModel):
    """Someone the caller has sent money to before."""

    card_number: str
    # As recorded when money was last sent to this card; null if unknown.
    display_name: str | None
    currency: str
    last_sent_at: datetime


class CreateMerchantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class MerchantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: UUID
    name: str
    status: MerchantStatus
    created_at: datetime


class CreatePaymentRequest(BaseModel):
    source_wallet_id: UUID
    merchant_id: UUID
    # Decimal string at the API boundary, never a JSON number (ADR-0001).
    amount: str = Field(min_length=1, max_length=32)
    currency: str = Field(min_length=3, max_length=3)
    description: str | None = Field(default=None, max_length=255)


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    source_wallet_id: UUID
    merchant_id: UUID
    amount_minor: int
    currency: str
    status: PaymentStatus
    failure_reason: str | None
    fraud_decision: FraudDecision | None
    refunded_amount_minor: int
    description: str | None
    # Set for a payment to a service provider: which one, and the
    # customer's account there.
    service_code: str | None = None
    service_account: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class CreateRefundRequest(BaseModel):
    # Decimal string at the API boundary, never a JSON number (ADR-0001).
    amount: str = Field(min_length=1, max_length=32)
    reason: str | None = Field(default=None, max_length=255)


class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_id: UUID
    amount_minor: int
    reason: str | None
    status: RefundStatus
    failure_reason: str | None
    created_at: datetime


class TransactionType(enum.StrEnum):
    """The kind of business operation a transaction summarizes (spec
    Section 20's API map).
    """

    TRANSFER = "TRANSFER"
    PAYMENT = "PAYMENT"
    EXCHANGE = "EXCHANGE"


class TransactionDirection(enum.StrEnum):
    # Money leaving the caller (a transfer or payment they started).
    OUT = "OUT"
    # Money reaching the caller (a transfer someone sent them).
    IN = "IN"
    # Money moved between the caller's own wallets (a currency exchange).
    SELF = "SELF"


class TransactionResponse(BaseModel):
    """A type-erased view over any business operation (Transfer or
    Payment) for the user-facing history endpoints
    (`GET /api/v1/transactions[/{id}]`) — distinct from
    `TransferResponse`/`PaymentResponse`, which are type-specific and
    used by their own APIs.
    """

    id: UUID
    type: TransactionType
    direction: TransactionDirection
    # The other person, as "First L.": the recipient of a transfer the
    # caller sent, or the sender of one they received. Null for payments
    # and when it isn't known.
    counterparty_name: str | None
    reference: str
    status: str
    amount_minor: int
    currency: str
    description: str | None
    # For an exchange: what `amount_minor` of `currency` was exchanged
    # for. Null for transfers and payments.
    received_amount_minor: int | None = None
    received_currency: str | None = None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_transfer(cls, transfer: Transfer, *, viewer_user_id: UUID) -> "TransactionResponse":
        incoming = transfer.initiator_user_id != viewer_user_id
        return cls(
            id=transfer.id,
            type=TransactionType.TRANSFER,
            direction=TransactionDirection.IN if incoming else TransactionDirection.OUT,
            counterparty_name=transfer.sender_name if incoming else transfer.recipient_name,
            reference=transfer.reference,
            status=transfer.status.value,
            amount_minor=transfer.amount_minor,
            currency=transfer.currency,
            description=transfer.description,
            created_at=transfer.created_at,
            completed_at=transfer.completed_at,
        )

    @classmethod
    def from_exchange(cls, exchange: Exchange) -> "TransactionResponse":
        return cls(
            id=exchange.id,
            type=TransactionType.EXCHANGE,
            direction=TransactionDirection.SELF,
            counterparty_name=None,
            reference=exchange.reference,
            # The saga's intermediate steps are one thing to a customer:
            # it is being carried out.
            status=exchange.status.value
            if exchange.status in (ExchangeStatus.COMPLETED, ExchangeStatus.FAILED)
            else "PROCESSING",
            amount_minor=exchange.source_amount_minor,
            currency=exchange.source_currency,
            received_amount_minor=exchange.destination_amount_minor,
            received_currency=exchange.destination_currency,
            description=None,
            created_at=exchange.created_at,
            completed_at=exchange.completed_at,
        )

    @classmethod
    def from_payment(cls, payment: Payment) -> "TransactionResponse":
        return cls(
            id=payment.id,
            type=TransactionType.PAYMENT,
            direction=TransactionDirection.OUT,
            counterparty_name=None,
            reference=payment.reference,
            status=payment.status.value,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            description=payment.description,
            created_at=payment.created_at,
            completed_at=payment.completed_at,
        )


class AdminTransactionResponse(TransactionResponse):
    """TransactionResponse plus what staff need and a user's own history
    doesn't show: whose operation it is, where the money was headed, and
    the fraud/review trail (the admin panel, ADR-0005).
    """

    initiator_user_id: UUID
    source_wallet_id: UUID
    # The destination wallet for a TRANSFER, the merchant for a PAYMENT.
    counterparty_id: UUID
    failure_reason: str | None
    fraud_decision: FraudDecision | None
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    updated_at: datetime

    @classmethod
    def from_operation(cls, operation: Transfer | Payment) -> "AdminTransactionResponse":
        if isinstance(operation, Transfer):
            # The console looks at an operation from its initiator's side.
            base = TransactionResponse.from_transfer(
                operation, viewer_user_id=operation.initiator_user_id
            )
            counterparty_id = operation.destination_wallet_id
        else:
            base = TransactionResponse.from_payment(operation)
            counterparty_id = operation.merchant_id
        return cls(
            **base.model_dump(),
            initiator_user_id=operation.initiator_user_id,
            source_wallet_id=operation.source_wallet_id,
            counterparty_id=counterparty_id,
            failure_reason=operation.failure_reason,
            fraud_decision=operation.fraud_decision,
            reviewed_by_user_id=operation.reviewed_by_user_id,
            reviewed_at=operation.reviewed_at,
            updated_at=operation.updated_at,
        )


class ReviewDecisionRequest(BaseModel):
    decision: ReviewDecision
