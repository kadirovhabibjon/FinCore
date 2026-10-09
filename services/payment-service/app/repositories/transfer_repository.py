from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.transfer import FraudDecision, Transfer, TransferStatus


class TransferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, transfer_id: UUID) -> Transfer | None:
        return await self._session.get(Transfer, transfer_id)

    async def list_for_user(
        self, user_id: UUID, *, limit: int, offset: int, where: Sequence[Any] = ()
    ) -> list[Transfer]:
        """Newest first - the user's own transaction history (spec
        Section 20's `GET /api/v1/transactions`): every transfer they
        started, whatever became of it, and every transfer that reached
        them. One that failed or is still in review never reached the
        recipient, so they don't see it.
        """
        result = await self._session.execute(
            select(Transfer)
            .where(
                or_(
                    Transfer.initiator_user_id == user_id,
                    and_(
                        Transfer.recipient_user_id == user_id,
                        Transfer.status == TransferStatus.COMPLETED,
                    ),
                ),
                # A narrower view of the same history (app/services/history.py).
                *where,
            )
            .order_by(Transfer.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_recent_recipients(self, user_id: UUID, *, limit: int) -> list[Transfer]:
        """The newest completed transfer to each card the user has sent
        money to, most recent card first."""
        newest = (
            select(
                Transfer.id,
                func.row_number()
                .over(
                    partition_by=Transfer.recipient_card_number,
                    order_by=Transfer.created_at.desc(),
                )
                .label("position"),
            )
            .where(
                Transfer.initiator_user_id == user_id,
                Transfer.status == TransferStatus.COMPLETED,
                Transfer.recipient_card_number.is_not(None),
            )
            .subquery()
        )
        result = await self._session.execute(
            select(Transfer)
            .join(newest, newest.c.id == Transfer.id)
            .where(newest.c.position == 1)
            .order_by(Transfer.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_stuck_processing(self, *, older_than: datetime) -> list[Transfer]:
        """Transfers left in PROCESSING by an unknown ledger outcome
        (spec Section 10.1) whose last update is older than `older_than`
        — recent ones are left alone since the original request may
        still be in flight. Used by the recovery worker.
        """
        result = await self._session.execute(
            select(Transfer)
            .where(Transfer.status == TransferStatus.PROCESSING, Transfer.updated_at < older_than)
            .order_by(Transfer.updated_at)
        )
        return list(result.scalars().all())

    async def list_awaiting_review(self, *, limit: int) -> list[Transfer]:
        """Oldest first — the review queue is worked in arrival order."""
        result = await self._session.execute(
            select(Transfer)
            .where(
                Transfer.status == TransferStatus.PENDING,
                Transfer.fraud_decision == FraudDecision.REVIEW,
                Transfer.reviewed_at.is_(None),
            )
            .order_by(Transfer.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_all(
        self,
        *,
        status: TransferStatus | None,
        user_id: UUID | None,
        limit: int,
        offset: int,
    ) -> list[Transfer]:
        """Newest first across every user — the admin transactions view."""
        query = select(Transfer)
        if status is not None:
            query = query.where(Transfer.status == status)
        if user_id is not None:
            query = query.where(Transfer.initiator_user_id == user_id)
        result = await self._session.execute(
            query.order_by(Transfer.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def resolve_review(
        self,
        transfer_id: UUID,
        *,
        new_status: TransferStatus,
        reviewer_id: UUID,
        reviewed_at: datetime,
        **extra_fields: Any,
    ) -> bool:
        """Moves a transfer out of fraud review — the same atomic-guard
        idea as `transition_status`, but also requiring the REVIEW
        decision and an unset `reviewed_at`: a PENDING transfer without
        REVIEW is one whose fraud check is still in flight, and two
        reviewers racing on the same item must not both win.
        """
        result = await self._session.execute(
            update(Transfer)
            .where(
                Transfer.id == transfer_id,
                Transfer.status == TransferStatus.PENDING,
                Transfer.fraud_decision == FraudDecision.REVIEW,
                Transfer.reviewed_at.is_(None),
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
        transfer_id: UUID,
        *,
        expected: TransferStatus,
        new_status: TransferStatus,
        **extra_fields: Any,
    ) -> bool:
        """Atomic `WHERE status = :expected` guard (spec Section 7.3) — the
        state machine is enforced by the database update itself, not
        assumed from whatever the caller last read into memory.

        Returns whether the transition was actually applied. A caller
        that gets `False` back is racing something else that already
        moved this transfer past `expected`; it must re-read the row
        rather than assume its own intended transition happened.
        """
        result = await self._session.execute(
            update(Transfer)
            .where(Transfer.id == transfer_id, Transfer.status == expected)
            .values(status=new_status, **extra_fields)
        )
        return result.rowcount == 1  # type: ignore[attr-defined]
