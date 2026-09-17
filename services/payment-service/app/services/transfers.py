from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import SameWalletTransferError
from app.domain.transfer import FraudDecision, Transfer, TransferStatus
from app.repositories.transfer_repository import TransferRepository
from app.services import fraud, ledger
from app.services.ledger import PostingOutcome


@dataclass(frozen=True)
class CreateTransferInput:
    initiator_user_id: UUID
    idempotency_key_id: UUID
    source_wallet_id: UUID
    destination_wallet_id: UUID
    amount_minor: int
    currency: str
    description: str | None = None


async def create_transfer(session: AsyncSession, data: CreateTransferInput) -> Transfer:
    """Creates a Transfer and runs the saga to its first stopping point
    (spec Section 10.1):

      fraud BLOCK              -> FAILED
      fraud REVIEW              -> stays PENDING
      fraud unreachable          -> fail-open/fail-closed policy decides (app/services/fraud.py)
      ledger posting succeeds    -> COMPLETED
      ledger business rejection  -> FAILED (e.g. insufficient funds)
      ledger unreachable/timeout -> stays PROCESSING ("unknown outcome" —
                                     never FAILED; the recovery worker
                                     resolves this later by retrying the
                                     same source_id, which is safe because
                                     ledger-service's posting endpoint is
                                     idempotent on it)

    Every branch returns normally — landing in any of these states is the
    saga working correctly for that outcome, not this function failing.
    """
    if data.source_wallet_id == data.destination_wallet_id:
        raise SameWalletTransferError("source and destination wallets must differ")

    transfer = Transfer(
        initiator_user_id=data.initiator_user_id,
        source_wallet_id=data.source_wallet_id,
        destination_wallet_id=data.destination_wallet_id,
        amount_minor=data.amount_minor,
        currency=data.currency,
        description=data.description,
        idempotency_key_id=data.idempotency_key_id,
    )
    session.add(transfer)
    await session.commit()
    await session.refresh(transfer)

    return await _advance_saga(session, transfer)


async def _advance_saga(session: AsyncSession, transfer: Transfer) -> Transfer:
    repository = TransferRepository(session)

    fraud_result = await fraud.fraud_client.check(
        user_id=transfer.initiator_user_id,
        amount_minor=transfer.amount_minor,
        currency=transfer.currency,
        operation_type="TRANSFER",
        operation_id=transfer.id,
    )

    if fraud_result.decision == FraudDecision.BLOCK:
        await repository.transition_status(
            transfer.id,
            expected=TransferStatus.PENDING,
            new_status=TransferStatus.FAILED,
            failure_reason="blocked by fraud check",
            fraud_decision=FraudDecision.BLOCK,
        )
        await session.commit()
        await session.refresh(transfer)
        return transfer

    if fraud_result.decision == FraudDecision.REVIEW:
        await repository.transition_status(
            transfer.id,
            expected=TransferStatus.PENDING,
            new_status=TransferStatus.PENDING,
            fraud_decision=FraudDecision.REVIEW,
        )
        await session.commit()
        await session.refresh(transfer)
        return transfer

    # ALLOW: PENDING -> PROCESSING, then attempt the actual money movement.
    await repository.transition_status(
        transfer.id,
        expected=TransferStatus.PENDING,
        new_status=TransferStatus.PROCESSING,
        fraud_decision=FraudDecision.ALLOW,
    )
    await session.commit()
    # The bulk UPDATE above expires this ORM instance's attributes; a
    # plain (unawaited) attribute read after that would hit SQLAlchemy's
    # "MissingGreenlet" guard against synchronous lazy-loading in an
    # async context. Refresh explicitly before reading anything off
    # `transfer` again, here and after every commit below.
    await session.refresh(transfer)

    posting_result = await ledger.ledger_client.create_posting(
        source_service="payment-service",
        source_id=str(transfer.id),
        type="TRANSFER",
        currency=transfer.currency,
        entries=[
            {
                "account_id": str(transfer.source_wallet_id),
                "direction": "DEBIT",
                "amount_minor": transfer.amount_minor,
            },
            {
                "account_id": str(transfer.destination_wallet_id),
                "direction": "CREDIT",
                "amount_minor": transfer.amount_minor,
            },
        ],
    )

    if posting_result.outcome == PostingOutcome.SUCCESS:
        await repository.transition_status(
            transfer.id,
            expected=TransferStatus.PROCESSING,
            new_status=TransferStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await session.commit()
        await session.refresh(transfer)
    elif posting_result.outcome == PostingOutcome.BUSINESS_REJECTION:
        await repository.transition_status(
            transfer.id,
            expected=TransferStatus.PROCESSING,
            new_status=TransferStatus.FAILED,
            failure_reason=posting_result.failure_reason,
        )
        await session.commit()
        await session.refresh(transfer)
    # else UNKNOWN: leave the transfer PROCESSING, untouched — `transfer`
    # in memory already reflects PROCESSING from the refresh above.

    return transfer
