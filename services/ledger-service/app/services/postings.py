from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AccountNotActiveError,
    CurrencyMismatchError,
    InsufficientFundsError,
    UnbalancedPostingError,
    UnknownAccountError,
)
from app.domain.account import AccountKind, AccountStatus
from app.domain.posting import EntryDirection, LedgerEntry, Posting, PostingType
from app.repositories.account_repository import AccountRepository
from app.repositories.posting_repository import PostingRepository

# Normal balance side per account kind (ADR-0002). An entry on this side
# increases the account's balance; an entry on the other side decreases
# it. SUSPENSE has no fixed normal side in the spec — CREDIT is used here
# only as a bookkeeping convention for computing a delta, not a claim
# that SUSPENSE behaves like a liability account.
_NORMAL_SIDE: dict[AccountKind, EntryDirection] = {
    AccountKind.USER_WALLET: EntryDirection.CREDIT,
    AccountKind.MERCHANT_SETTLEMENT: EntryDirection.CREDIT,
    AccountKind.FEES: EntryDirection.CREDIT,
    AccountKind.EXTERNAL_FUNDING: EntryDirection.DEBIT,
    AccountKind.EXTERNAL_PAYOUT: EntryDirection.CREDIT,
    AccountKind.SUSPENSE: EntryDirection.CREDIT,
}


@dataclass(frozen=True)
class EntryInput:
    account_id: UUID
    direction: EntryDirection
    amount_minor: int


def _signed_delta(kind: AccountKind, direction: EntryDirection, amount_minor: int) -> int:
    normal_side = _NORMAL_SIDE[kind]
    return amount_minor if direction is normal_side else -amount_minor


async def create_posting(
    session: AsyncSession,
    *,
    source_service: str,
    source_id: str,
    type: PostingType,
    currency: str,
    entries: list[EntryInput],
) -> Posting:
    """Creates a balanced posting, or returns the existing one if this
    exact (source_service, source_id, type) was already posted.

    Implements ADR-0002's algorithm precisely:
      1. Idempotency check first — a retry must not re-validate or
         re-lock anything if the posting already exists.
      2. Validate debits == credits *before* taking any lock — no point
         locking accounts for a posting that's malformed regardless.
      3. Lock every involved account's balance, in ascending account_id
         order (via AccountRepository.lock_balances), so two postings
         touching the same two accounts in opposite "directions" can
         never deadlock each other.
      4. Only *after* the lock: check each account is ACTIVE, shares the
         posting's currency, and — for USER_WALLET accounts — that the
         resulting available balance would not go negative. This is the
         TOCTOU fix from the spec's revision notes: the balance check
         happens after the lock, inside this same transaction, never
         before it.
      5. Insert the posting + entries, apply the balance deltas, commit.
    """
    posting_repository = PostingRepository(session)

    existing = await posting_repository.get_by_source(source_service, source_id, type)
    if existing is not None:
        return existing

    _validate_balanced(entries, currency)

    account_ids = [entry.account_id for entry in entries]
    account_repository = AccountRepository(session)
    locked_balances = await account_repository.lock_balances(account_ids)
    accounts = await account_repository.get_accounts(account_ids)

    net_effect: dict[UUID, int] = {}
    for entry in entries:
        account = accounts.get(entry.account_id)
        if account is None:
            raise UnknownAccountError(str(entry.account_id))
        if account.currency != currency:
            raise CurrencyMismatchError(
                f"account {account.id} is {account.currency}, posting is {currency}"
            )
        if account.status != AccountStatus.ACTIVE:
            raise AccountNotActiveError(f"account {account.id} is {account.status.value}")

        delta = _signed_delta(account.kind, entry.direction, entry.amount_minor)
        net_effect[entry.account_id] = net_effect.get(entry.account_id, 0) + delta

    for account_id, delta in net_effect.items():
        balance = locked_balances[account_id]
        account = accounts[account_id]
        if account.kind == AccountKind.USER_WALLET:
            available_after = balance.balance_minor + delta - balance.held_minor
            if available_after < 0:
                raise InsufficientFundsError(f"account {account_id} would go negative")

    posting = Posting(
        source_service=source_service, source_id=source_id, type=type, currency=currency
    )
    session.add(posting)
    await session.flush()  # assign posting.id before entries reference it

    for entry in entries:
        session.add(
            LedgerEntry(
                posting_id=posting.id,
                account_id=entry.account_id,
                direction=entry.direction,
                amount_minor=entry.amount_minor,
                currency=currency,
            )
        )

    for account_id, delta in net_effect.items():
        balance = locked_balances[account_id]
        balance.balance_minor += delta
        balance.version += 1

    try:
        await session.commit()
    except IntegrityError:
        # Only reachable if a concurrent request for the *same* idempotency
        # key raced past our initial check and committed first — the
        # UNIQUE(source_service, source_id, type) constraint is the real
        # guard (Section 9's "let the database decide the race" pattern).
        await session.rollback()
        existing = await posting_repository.get_by_source(source_service, source_id, type)
        if existing is not None:
            return existing
        raise

    await session.refresh(posting)
    return posting


def _validate_balanced(entries: list[EntryInput], currency: str) -> None:
    if len(entries) < 2:
        raise UnbalancedPostingError("a posting needs at least two entries")

    debit_total = sum(e.amount_minor for e in entries if e.direction is EntryDirection.DEBIT)
    credit_total = sum(e.amount_minor for e in entries if e.direction is EntryDirection.CREDIT)
    if debit_total != credit_total:
        raise UnbalancedPostingError(
            f"debits ({debit_total}) != credits ({credit_total}) for currency {currency}"
        )
