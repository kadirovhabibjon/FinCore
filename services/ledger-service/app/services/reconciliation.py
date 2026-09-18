import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account import AccountKind, LedgerAccount
from app.domain.balance import AccountBalance
from app.domain.posting import EntryDirection, LedgerEntry, Posting
from app.services.postings import signed_delta

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationReport:
    """One reconciliation pass (spec Section 8.4, ADR-0002's
    "Reconciliation invariants"). Every field is independently re-derived
    from the append-only entry log — never trusted from the denormalized
    `account_balances` cache the job exists to check.

    A non-empty field is an incident to investigate, not a value this
    job ever silently corrects (ADR-0002).
    """

    unbalanced_postings: list[UUID] = field(default_factory=list)
    balance_mismatches: list[UUID] = field(default_factory=list)
    negative_available_wallets: list[UUID] = field(default_factory=list)
    duplicate_source_postings: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (
            self.unbalanced_postings
            or self.balance_mismatches
            or self.negative_available_wallets
            or self.duplicate_source_postings
        )


async def run_reconciliation(session: AsyncSession) -> ReconciliationReport:
    report = ReconciliationReport(
        unbalanced_postings=await _find_unbalanced_postings(session),
        balance_mismatches=await _find_balance_mismatches(session),
        negative_available_wallets=await _find_negative_available_wallets(session),
        duplicate_source_postings=await _find_duplicate_source_postings(session),
    )
    if not report.is_clean:
        logger.error("reconciliation found violations: %s", report)
    return report


async def _find_unbalanced_postings(session: AsyncSession) -> list[UUID]:
    """per posting: sum(debits) == sum(credits)."""
    debit_total = func.sum(
        case((LedgerEntry.direction == EntryDirection.DEBIT, LedgerEntry.amount_minor), else_=0)
    )
    credit_total = func.sum(
        case((LedgerEntry.direction == EntryDirection.CREDIT, LedgerEntry.amount_minor), else_=0)
    )
    stmt = (
        select(LedgerEntry.posting_id)
        .group_by(LedgerEntry.posting_id)
        .having(debit_total != credit_total)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _find_balance_mismatches(session: AsyncSession) -> list[UUID]:
    """per account: account_balances.balance_minor == sum of its entries,
    signed per the same convention `create_posting` used to apply them
    (app/services/postings.py's NORMAL_SIDE table) — recomputed
    independently here rather than trusted.
    """
    entries_stmt = select(
        LedgerEntry.account_id, LedgerEntry.direction, LedgerEntry.amount_minor, LedgerAccount.kind
    ).join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)

    computed_balances: dict[UUID, int] = {}
    for account_id, direction, amount_minor, kind in (await session.execute(entries_stmt)).all():
        computed_balances[account_id] = computed_balances.get(account_id, 0) + signed_delta(
            kind, direction, amount_minor
        )

    balances_stmt = select(AccountBalance.account_id, AccountBalance.balance_minor)
    mismatches = []
    for account_id, balance_minor in (await session.execute(balances_stmt)).all():
        if computed_balances.get(account_id, 0) != balance_minor:
            mismatches.append(account_id)
    return mismatches


async def _find_negative_available_wallets(session: AsyncSession) -> list[UUID]:
    """per wallet: balance_minor - held_minor >= 0. Already enforced by a
    CHECK constraint (app/domain/balance.py) — this independently
    verifies the same invariant as defense against a bug that somehow
    bypassed it.
    """
    stmt = select(AccountBalance.account_id).where(
        AccountBalance.kind == AccountKind.USER_WALLET,
        AccountBalance.balance_minor - AccountBalance.held_minor < 0,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _find_duplicate_source_postings(session: AsyncSession) -> list[tuple[str, str, str]]:
    """per transfer: at most one posting exists for its source_id.
    Already enforced by UNIQUE(source_service, source_id, type)
    (app/domain/posting.py) — same defense-in-depth reasoning as above.
    """
    stmt = (
        select(Posting.source_service, Posting.source_id, Posting.type)
        .group_by(Posting.source_service, Posting.source_id, Posting.type)
        .having(func.count() > 1)
    )
    result = await session.execute(stmt)
    return [
        (source_service, source_id, str(type_))
        for source_service, source_id, type_ in result.all()
    ]
