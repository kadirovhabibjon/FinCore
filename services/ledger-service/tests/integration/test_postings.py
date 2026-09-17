import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.core.exceptions import (
    AccountNotActiveError,
    CurrencyMismatchError,
    InsufficientFundsError,
    UnbalancedPostingError,
)
from app.db import session as db_session
from app.domain.account import AccountKind, AccountStatus, LedgerAccount
from app.domain.balance import AccountBalance
from app.domain.posting import EntryDirection, PostingType
from app.services.postings import EntryInput, create_posting

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _create_wallet(currency: str = "UZS") -> LedgerAccount:
    async with db_session.async_session_factory() as session:
        account = LedgerAccount(
            kind=AccountKind.USER_WALLET, owner_user_id=uuid.uuid4(), currency=currency
        )
        session.add(account)
        await session.flush()
        session.add(
            AccountBalance(account_id=account.id, kind=AccountKind.USER_WALLET)
        )
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


async def _balance(account_id: uuid.UUID) -> AccountBalance:
    async with db_session.async_session_factory() as session:
        balance = await session.get(AccountBalance, account_id)
        assert balance is not None
        return balance


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


async def test_deposit_credits_the_wallet_and_debits_external_funding() -> None:
    wallet = await _create_wallet()
    funding_id = await _system_account_id(AccountKind.EXTERNAL_FUNDING)

    await _deposit(wallet.id, 50_000_00, "dep-1")

    wallet_balance = await _balance(wallet.id)
    funding_balance = await _balance(funding_id)
    assert wallet_balance.balance_minor == 50_000_00
    assert funding_balance.balance_minor == 50_000_00  # DEBIT-normal: debit increases it


async def test_transfer_moves_money_between_two_wallets() -> None:
    sender = await _create_wallet()
    recipient = await _create_wallet()
    await _deposit(sender.id, 100_000_00, "dep-transfer-setup")

    async with db_session.async_session_factory() as session:
        await create_posting(
            session,
            source_service="payment-service",
            source_id="transfer-1",
            type=PostingType.TRANSFER,
            currency="UZS",
            entries=[
                EntryInput(sender.id, EntryDirection.DEBIT, 30_000_00),
                EntryInput(recipient.id, EntryDirection.CREDIT, 30_000_00),
            ],
        )

    sender_balance = await _balance(sender.id)
    recipient_balance = await _balance(recipient.id)
    assert sender_balance.balance_minor == 70_000_00
    assert recipient_balance.balance_minor == 30_000_00


async def test_posting_is_idempotent_on_source_service_source_id_type() -> None:
    sender = await _create_wallet()
    recipient = await _create_wallet()
    await _deposit(sender.id, 100_000_00, "dep-idem-setup")

    entries = [
        EntryInput(sender.id, EntryDirection.DEBIT, 10_000_00),
        EntryInput(recipient.id, EntryDirection.CREDIT, 10_000_00),
    ]

    async with db_session.async_session_factory() as session:
        first = await create_posting(
            session,
            source_service="payment-service",
            source_id="idempotent-transfer",
            type=PostingType.TRANSFER,
            currency="UZS",
            entries=entries,
        )
    async with db_session.async_session_factory() as session:
        second = await create_posting(
            session,
            source_service="payment-service",
            source_id="idempotent-transfer",
            type=PostingType.TRANSFER,
            currency="UZS",
            entries=entries,
        )

    assert first.id == second.id
    # Money moved exactly once, not twice.
    recipient_balance = await _balance(recipient.id)
    assert recipient_balance.balance_minor == 10_000_00


async def test_unbalanced_posting_is_rejected() -> None:
    sender = await _create_wallet()
    recipient = await _create_wallet()

    async with db_session.async_session_factory() as session:
        with pytest.raises(UnbalancedPostingError):
            await create_posting(
                session,
                source_service="test",
                source_id="unbalanced-1",
                type=PostingType.TRANSFER,
                currency="UZS",
                entries=[
                    EntryInput(sender.id, EntryDirection.DEBIT, 10_000_00),
                    EntryInput(recipient.id, EntryDirection.CREDIT, 9_000_00),
                ],
            )


async def test_currency_mismatch_is_rejected() -> None:
    uzs_wallet = await _create_wallet(currency="UZS")
    usd_wallet = await _create_wallet(currency="USD")

    async with db_session.async_session_factory() as session:
        with pytest.raises(CurrencyMismatchError):
            await create_posting(
                session,
                source_service="test",
                source_id="mismatch-1",
                type=PostingType.TRANSFER,
                currency="UZS",
                entries=[
                    EntryInput(uzs_wallet.id, EntryDirection.DEBIT, 1_000),
                    EntryInput(usd_wallet.id, EntryDirection.CREDIT, 1_000),
                ],
            )


async def test_insufficient_funds_is_rejected_and_nothing_moves() -> None:
    sender = await _create_wallet()
    recipient = await _create_wallet()
    await _deposit(sender.id, 5_000_00, "dep-insufficient-setup")

    async with db_session.async_session_factory() as session:
        with pytest.raises(InsufficientFundsError):
            await create_posting(
                session,
                source_service="test",
                source_id="overdraft-1",
                type=PostingType.TRANSFER,
                currency="UZS",
                entries=[
                    EntryInput(sender.id, EntryDirection.DEBIT, 10_000_00),
                    EntryInput(recipient.id, EntryDirection.CREDIT, 10_000_00),
                ],
            )

    # Rejected atomically: sender's balance is untouched.
    sender_balance = await _balance(sender.id)
    assert sender_balance.balance_minor == 5_000_00


async def test_frozen_wallet_cannot_participate_in_a_posting() -> None:
    sender = await _create_wallet()
    recipient = await _create_wallet()
    await _deposit(sender.id, 10_000_00, "dep-frozen-setup")

    async with db_session.async_session_factory() as session:
        account = await session.get(LedgerAccount, sender.id)
        assert account is not None
        account.status = AccountStatus.FROZEN
        await session.commit()

    async with db_session.async_session_factory() as session:
        with pytest.raises(AccountNotActiveError):
            await create_posting(
                session,
                source_service="test",
                source_id="frozen-1",
                type=PostingType.TRANSFER,
                currency="UZS",
                entries=[
                    EntryInput(sender.id, EntryDirection.DEBIT, 1_000_00),
                    EntryInput(recipient.id, EntryDirection.CREDIT, 1_000_00),
                ],
            )


async def test_opposite_direction_transfers_between_the_same_two_wallets_do_not_deadlock() -> None:
    """The scenario ADR-0002's lock ordering exists for: A -> B and B -> A
    concurrently. Without a deterministic lock order, one transaction
    could lock A then wait for B while the other locks B then waits for
    A — a classic deadlock. Both must complete (or fail on business
    grounds like insufficient funds), never hang or deadlock-abort.
    """
    wallet_a = await _create_wallet()
    wallet_b = await _create_wallet()
    await _deposit(wallet_a.id, 100_000_00, "dep-deadlock-a")
    await _deposit(wallet_b.id, 100_000_00, "dep-deadlock-b")

    async def a_to_b() -> None:
        async with db_session.async_session_factory() as session:
            await create_posting(
                session,
                source_service="test",
                source_id="deadlock-a-to-b",
                type=PostingType.TRANSFER,
                currency="UZS",
                entries=[
                    EntryInput(wallet_a.id, EntryDirection.DEBIT, 10_000_00),
                    EntryInput(wallet_b.id, EntryDirection.CREDIT, 10_000_00),
                ],
            )

    async def b_to_a() -> None:
        async with db_session.async_session_factory() as session:
            await create_posting(
                session,
                source_service="test",
                source_id="deadlock-b-to-a",
                type=PostingType.TRANSFER,
                currency="UZS",
                entries=[
                    EntryInput(wallet_b.id, EntryDirection.DEBIT, 20_000_00),
                    EntryInput(wallet_a.id, EntryDirection.CREDIT, 20_000_00),
                ],
            )

    # asyncio.wait_for as a safety net: if lock ordering were broken and
    # a real deadlock occurred, PostgreSQL would eventually abort one
    # side with a deadlock_detected error rather than hang forever, but
    # bounding this in the test makes a regression fail fast and clearly
    # instead of hanging CI.
    await asyncio.wait_for(asyncio.gather(a_to_b(), b_to_a()), timeout=10)

    balance_a = await _balance(wallet_a.id)
    balance_b = await _balance(wallet_b.id)
    # a sent 10k, received 20k -> net +10k; b sent 20k, received 10k -> net -10k
    assert balance_a.balance_minor == 100_000_00 + 10_000_00
    assert balance_b.balance_minor == 100_000_00 - 10_000_00
