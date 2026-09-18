import uuid

import pytest
from sqlalchemy import select, text

from app.db import session as db_session
from app.domain.account import AccountKind, LedgerAccount
from app.domain.balance import AccountBalance
from app.domain.posting import EntryDirection, LedgerEntry, Posting, PostingType
from app.services.postings import EntryInput, create_posting
from app.services.reconciliation import run_reconciliation

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _create_wallet(currency: str = "UZS") -> LedgerAccount:
    async with db_session.async_session_factory() as session:
        account = LedgerAccount(
            kind=AccountKind.USER_WALLET, owner_user_id=uuid.uuid4(), currency=currency
        )
        session.add(account)
        await session.flush()
        session.add(AccountBalance(account_id=account.id, kind=AccountKind.USER_WALLET))
        await session.commit()
        await session.refresh(account)
        return account


async def _system_account_id(kind: AccountKind, currency: str = "UZS") -> uuid.UUID:
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(LedgerAccount).where(
                LedgerAccount.kind == kind, LedgerAccount.currency == currency
            )
        )
        return result.scalar_one().id


async def _deposit(wallet_id: uuid.UUID, amount_minor: int, source_id: str) -> None:
    funding_id = await _system_account_id(AccountKind.EXTERNAL_FUNDING)
    async with db_session.async_session_factory() as session:
        await create_posting(
            session,
            source_service="test",
            source_id=source_id,
            type=PostingType.DEPOSIT,
            currency="UZS",
            entries=[
                EntryInput(funding_id, EntryDirection.DEBIT, amount_minor),
                EntryInput(wallet_id, EntryDirection.CREDIT, amount_minor),
            ],
        )


async def test_a_healthy_ledger_reports_no_violations() -> None:
    sender = await _create_wallet()
    recipient = await _create_wallet()
    await _deposit(sender.id, 100_000_00, "dep-1")

    async with db_session.async_session_factory() as session:
        await create_posting(
            session,
            source_service="payment-service",
            source_id="transfer-1",
            type=PostingType.TRANSFER,
            currency="UZS",
            entries=[
                EntryInput(sender.id, EntryDirection.DEBIT, 25_000_00),
                EntryInput(recipient.id, EntryDirection.CREDIT, 25_000_00),
            ],
        )

    async with db_session.async_session_factory() as session:
        report = await run_reconciliation(session)

    assert report.is_clean


async def test_detects_an_unbalanced_posting() -> None:
    """Bypasses `create_posting` (which would reject this) by inserting
    the posting and its mismatched entries directly, to prove the
    reconciliation job independently re-verifies "debits == credits"
    rather than trusting that every write went through the one code path
    that normally enforces it.
    """
    wallet = await _create_wallet()
    funding_id = await _system_account_id(AccountKind.EXTERNAL_FUNDING)

    async with db_session.async_session_factory() as session:
        posting = Posting(
            source_service="test", source_id="bad-1", type=PostingType.DEPOSIT, currency="UZS"
        )
        session.add(posting)
        await session.flush()
        session.add_all(
            [
                LedgerEntry(
                    posting_id=posting.id,
                    account_id=funding_id,
                    direction=EntryDirection.DEBIT,
                    amount_minor=100_00,
                    currency="UZS",
                ),
                LedgerEntry(
                    posting_id=posting.id,
                    account_id=wallet.id,
                    direction=EntryDirection.CREDIT,
                    amount_minor=50_00,  # deliberately unbalanced
                    currency="UZS",
                ),
            ]
        )
        await session.commit()
        posting_id = posting.id

    async with db_session.async_session_factory() as session:
        report = await run_reconciliation(session)

    assert report.unbalanced_postings == [posting_id]
    assert not report.is_clean


async def test_detects_a_balance_mismatch() -> None:
    """Directly corrupts the denormalized `account_balances` cache (which
    only `create_posting`'s atomic update is ever supposed to touch) to
    prove reconciliation catches drift between it and the entry log.
    """
    wallet = await _create_wallet()
    await _deposit(wallet.id, 50_000_00, "dep-mismatch")

    async with db_session.async_session_factory() as session:
        await session.execute(
            text("UPDATE account_balances SET balance_minor = 999999 WHERE account_id = :id"),
            {"id": wallet.id},
        )
        await session.commit()

    async with db_session.async_session_factory() as session:
        report = await run_reconciliation(session)

    assert report.balance_mismatches == [wallet.id]
    assert not report.is_clean


async def test_detects_a_negative_available_wallet() -> None:
    """The `balance_minor - held_minor >= 0` invariant is normally
    enforced by a CHECK constraint, so it can only be violated at all by
    first dropping that constraint here — proving reconciliation's own
    check is a real, working second line of defense, not dead code.
    `migrated_database` rebuilds the schema (constraint included) fresh
    for the next test, so this doesn't leak.
    """
    wallet = await _create_wallet()
    await _deposit(wallet.id, 10_000_00, "dep-negative")

    async with db_session.async_session_factory() as session:
        await session.execute(
            text(
                "ALTER TABLE account_balances "
                "DROP CONSTRAINT ck_account_balances_wallet_available_non_negative"
            )
        )
        await session.execute(
            text(
                "UPDATE account_balances SET held_minor = balance_minor + 1 "
                "WHERE account_id = :id"
            ),
            {"id": wallet.id},
        )
        await session.commit()

    async with db_session.async_session_factory() as session:
        report = await run_reconciliation(session)

    assert report.negative_available_wallets == [wallet.id]
    assert not report.is_clean


async def test_detects_duplicate_source_postings() -> None:
    """Same reasoning as the negative-wallet test: the UNIQUE constraint
    normally makes this impossible, so it's dropped here to prove
    reconciliation's own duplicate check actually fires.
    """
    wallet = await _create_wallet()
    funding_id = await _system_account_id(AccountKind.EXTERNAL_FUNDING)

    async with db_session.async_session_factory() as session:
        await session.execute(
            text("ALTER TABLE postings DROP CONSTRAINT uq_postings_source_idempotency")
        )
        for _ in range(2):
            posting = Posting(
                source_service="test", source_id="dup-1", type=PostingType.DEPOSIT, currency="UZS"
            )
            session.add(posting)
            await session.flush()
            session.add_all(
                [
                    LedgerEntry(
                        posting_id=posting.id,
                        account_id=funding_id,
                        direction=EntryDirection.DEBIT,
                        amount_minor=10_00,
                        currency="UZS",
                    ),
                    LedgerEntry(
                        posting_id=posting.id,
                        account_id=wallet.id,
                        direction=EntryDirection.CREDIT,
                        amount_minor=10_00,
                        currency="UZS",
                    ),
                ]
            )
        await session.commit()

    async with db_session.async_session_factory() as session:
        report = await run_reconciliation(session)

    assert report.duplicate_source_postings == [("test", "dup-1", "DEPOSIT")]
    assert not report.is_clean
