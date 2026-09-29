from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import FraudDecision


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, payment_id: UUID) -> Payment | None:
        return await self._session.get(Payment, payment_id)

    async def list_for_user(self, user_id: UUID, *, limit: int, offset: int) -> list[Payment]:
        """Newest first — the user's own transaction history (spec
        Section 20's `GET /api/v1/transactions`).
        """
        result = await self._session.execute(
            select(Payment)
            .where(Payment.initiator_user_id == user_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_stuck_processing(self, *, older_than: datetime) -> list[Payment]:
        """Payments left in PROCESSING by an unknown ledger outcome (a
        hold or capture call that timed out) whose last update is older
        than `older_than`. Used by the recovery worker.
        """
        result = await self._session.execute(
            select(Payment)
            .where(Payment.status == PaymentStatus.PROCESSING, Payment.updated_at < older_than)
            .order_by(Payment.updated_at)
        )
        return list(result.scalars().all())

    async def list_stale_created(self, *, older_than: datetime) -> list[Payment]:
        """CREATED payments that never advanced (most likely stuck
        awaiting a fraud REVIEW that was never resolved) past their
        review window. Used by the expiration worker.
        """
        result = await self._session.execute(
            select(Payment)
            .where(Payment.status == PaymentStatus.CREATED, Payment.created_at < older_than)
            .order_by(Payment.created_at)
        )
        return list(result.scalars().all())

    async def list_awaiting_review(self, *, limit: int) -> list[Payment]:
        """Oldest first — also the order the expiration worker will
        expire them in, so the queue shows the most urgent items first.
        """
        result = await self._session.execute(
            select(Payment)
            .where(
                Payment.status == PaymentStatus.CREATED,
                Payment.fraud_decision == FraudDecision.REVIEW,
                Payment.reviewed_at.is_(None),
            )
            .order_by(Payment.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_all(
        self,
        *,
        status: PaymentStatus | None,
        user_id: UUID | None,
        limit: int,
        offset: int,
    ) -> list[Payment]:
        """Newest first across every user — the admin transactions view."""
        query = select(Payment)
        if status is not None:
            query = query.where(Payment.status == status)
        if user_id is not None:
            query = query.where(Payment.initiator_user_id == user_id)
        result = await self._session.execute(
            query.order_by(Payment.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def resolve_review(
        self,
        payment_id: UUID,
        *,
        new_status: PaymentStatus,
        reviewer_id: UUID,
        reviewed_at: datetime,
        **extra_fields: Any,
    ) -> bool:
        """Same guard as TransferRepository.resolve_review. The CREATED
        condition also makes approval lose cleanly to the expiration
        worker: once a payment is EXPIRED this matches nothing.
        """
        result = await self._session.execute(
            update(Payment)
            .where(
                Payment.id == payment_id,
                Payment.status == PaymentStatus.CREATED,
                Payment.fraud_decision == FraudDecision.REVIEW,
                Payment.reviewed_at.is_(None),
            )
            .values(
                status=new_status,
                reviewed_by_user_id=reviewer_id,
                reviewed_at=reviewed_at,
                **extra_fields,
            )
        )
        return result.rowcount == 1  # type: ignore[attr-defined]

    async def transition_status(
        self,
        payment_id: UUID,
        *,
        expected: PaymentStatus,
        new_status: PaymentStatus,
        **extra_fields: Any,
    ) -> bool:
        """Atomic `WHERE status = :expected` guard (spec Section 7.3,
        mirroring TransferRepository exactly) — the state machine is
        enforced by the database update itself, not assumed from
        whatever the caller last read into memory.
        """
        result = await self._session.execute(
            update(Payment)
            .where(Payment.id == payment_id, Payment.status == expected)
            .values(status=new_status, **extra_fields)
        )
        return result.rowcount == 1  # type: ignore[attr-defined]

    async def add_refunded_amount(self, payment_id: UUID, amount_minor: int) -> bool:
        """Atomic increment guarded by the same CHECK constraint the
        column already has (`refunded_amount_minor <= amount_minor`) —
        an attempt that would push the running total over the captured
        amount fails at the database, not in application code (spec
        Section 11: "total refunds <= captured amount").
        """
        result = await self._session.execute(
            update(Payment)
            .where(Payment.id == payment_id)
            .values(refunded_amount_minor=Payment.refunded_amount_minor + amount_minor)
        )
        return result.rowcount == 1  # type: ignore[attr-defined]
