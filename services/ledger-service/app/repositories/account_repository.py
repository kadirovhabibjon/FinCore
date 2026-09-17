from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account import AccountKind, LedgerAccount
from app.domain.balance import AccountBalance
from app.domain.posting import LedgerEntry


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_accounts(self, account_ids: Iterable[UUID]) -> dict[UUID, LedgerAccount]:
        """Plain (unlocked) read of account metadata: kind, currency,
        status. Not locked because kind/currency are immutable and status
        changes are rare/administrative — the invariant that actually
        needs protecting under concurrency is the balance, not this.
        """
        ids = list(set(account_ids))
        result = await self._session.execute(
            select(LedgerAccount).where(LedgerAccount.id.in_(ids))
        )
        return {account.id: account for account in result.scalars().all()}

    async def lock_balances(self, account_ids: Iterable[UUID]) -> dict[UUID, AccountBalance]:
        """Locks each account's balance row with `SELECT ... FOR UPDATE`,
        one at a time, in ascending account_id order (ADR-0002).

        Issued as separate sequential statements rather than one
        multi-row `WHERE id IN (...) FOR UPDATE` query on purpose:
        PostgreSQL does not guarantee that a single query's internal row
        processing follows an ORDER BY when acquiring row locks, so that
        wouldn't actually guarantee the lock *acquisition* order — only
        issuing the locks one at a time, in a query per account, does.
        This is what makes two transfers between the same two wallets in
        opposite directions unable to deadlock each other.
        """
        locked: dict[UUID, AccountBalance] = {}
        for account_id in sorted(set(account_ids)):
            balance = await self._session.get(
                AccountBalance, account_id, with_for_update=True
            )
            if balance is not None:
                locked[account_id] = balance
        return locked

    async def get_wallets_for_user(self, user_id: UUID) -> list[LedgerAccount]:
        result = await self._session.execute(
            select(LedgerAccount).where(
                LedgerAccount.owner_user_id == user_id,
                LedgerAccount.kind == AccountKind.USER_WALLET,
            )
        )
        return list(result.scalars().all())

    async def get_wallet_by_id(self, wallet_id: UUID) -> LedgerAccount | None:
        account = await self._session.get(LedgerAccount, wallet_id)
        if account is not None and account.kind != AccountKind.USER_WALLET:
            return None
        return account

    async def get_entries_for_account(
        self, account_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[LedgerEntry]:
        result = await self._session.execute(
            select(LedgerEntry)
            .where(LedgerEntry.account_id == account_id)
            .order_by(LedgerEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
