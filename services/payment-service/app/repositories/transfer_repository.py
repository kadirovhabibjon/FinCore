from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.transfer import Transfer, TransferStatus


class TransferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, transfer_id: UUID) -> Transfer | None:
        return await self._session.get(Transfer, transfer_id)

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
