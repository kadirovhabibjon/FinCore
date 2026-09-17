from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.transfer import Transfer, TransferStatus


class TransferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, transfer_id: UUID) -> Transfer | None:
        return await self._session.get(Transfer, transfer_id)

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
