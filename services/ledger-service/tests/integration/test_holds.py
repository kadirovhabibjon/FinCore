import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.exceptions import (
    CaptureExceedsHoldError,
    HoldExpiredError,
    HoldNotFoundError,
)
from app.db import session as db_session
from app.domain.account import AccountKind, LedgerAccount
from app.domain.balance import AccountBalance
from app.domain.hold import Hold, HoldStatus
from app.domain.posting import EntryDirection, PostingType
from app.services.holds import capture_hold, create_hold, release_hold
from app.services.postings import EntryInput, create_posting

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _create_funded_wallet(amount_minor: int, currency: str = "UZS") -> LedgerAccount:
    async with db_session.async_session_factory() as session:
        account = LedgerAccount(
            kind=AccountKind.USER_WALLET, owner_user_id=uuid.uuid4(), currency=currency
        )
        session.add(account)
        await session.flush()
        session.add(AccountBalance(account_id=account.id, kind=AccountKind.USER_WALLET))
        await session.commit()
        await session.refresh(account)

    funding_id = await _system_account_id(AccountKind.EXTERNAL_FUNDING, currency)
    async with db_session.async_session_factory() as session:
        await create_posting(
            session,
            source_service="test",
            source_id=f"fund-{account.id}",
            type=PostingType.DEPOSIT,
            currency=currency,
            entries=[
                EntryInput(funding_id, EntryDirection.DEBIT, amount_minor),
                EntryInput(account.id, EntryDirection.CREDIT, amount_minor),
            ],
        )
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


async def test_create_hold_reserves_without_moving_money() -> None:
    wallet = await _create_funded_wallet(100_000_00)

    async with db_session.async_session_factory() as session:
        hold = await create_hold(
            session,
            source_service="payment-service",
            source_id="hold-1",
            account_id=wallet.id,
            amount_minor=30_000_00,
            currency="UZS",
            ttl_seconds=900,
        )

    assert hold.status == HoldStatus.ACTIVE
    balance = await _balance(wallet.id)
    assert balance.balance_minor == 100_000_00  # unchanged — no posting yet
    assert balance.held_minor == 30_000_00


async def test_create_hold_is_idempotent() -> None:
    wallet = await _create_funded_wallet(50_000_00)

    async with db_session.async_session_factory() as session:
        first = await create_hold(
            session,
            source_service="payment-service",
            source_id="hold-idem",
            account_id=wallet.id,
            amount_minor=10_000_00,
            currency="UZS",
            ttl_seconds=900,
        )
    async with db_session.async_session_factory() as session:
        second = await create_hold(
            session,
            source_service="payment-service",
            source_id="hold-idem",
            account_id=wallet.id,
            amount_minor=10_000_00,
            currency="UZS",
            ttl_seconds=900,
        )

    assert first.id == second.id
    balance = await _balance(wallet.id)
    assert balance.held_minor == 10_000_00  # reserved exactly once


async def test_capture_hold_moves_money_to_merchant_settlement() -> None:
    wallet = await _create_funded_wallet(100_000_00)
    merchant_id = await _system_account_id(AccountKind.MERCHANT_SETTLEMENT)

    async with db_session.async_session_factory() as session:
        hold = await create_hold(
            session,
            source_service="payment-service",
            source_id="hold-capture-1",
            account_id=wallet.id,
            amount_minor=20_000_00,
            currency="UZS",
            ttl_seconds=900,
        )

    async with db_session.async_session_factory() as session:
        posting = await capture_hold(
            session,
            hold.id,
            amount_minor=20_000_00,
            source_service="payment-service",
            source_id="capture-1",
        )

    assert posting.type == PostingType.PAYMENT
    wallet_balance = await _balance(wallet.id)
    merchant_balance = await _balance(merchant_id)
    assert wallet_balance.balance_minor == 80_000_00
    assert wallet_balance.held_minor == 0  # fully released by the capture
    assert merchant_balance.balance_minor == 20_000_00


async def test_partial_capture_releases_the_remainder() -> None:
    """ADR-0002: "a capture for less than the held amount releases the
    remainder" — held_minor drops by the *original hold amount*, not
    just the captured portion.
    """
    wallet = await _create_funded_wallet(100_000_00)

    async with db_session.async_session_factory() as session:
        hold = await create_hold(
            session,
            source_service="payment-service",
            source_id="hold-partial-1",
            account_id=wallet.id,
            amount_minor=50_000_00,
            currency="UZS",
            ttl_seconds=900,
        )

    async with db_session.async_session_factory() as session:
        await capture_hold(
            session,
            hold.id,
            amount_minor=30_000_00,  # less than the 50k held
            source_service="payment-service",
            source_id="capture-partial-1",
        )

    wallet_balance = await _balance(wallet.id)
    assert wallet_balance.balance_minor == 70_000_00  # 100k - 30k captured
    assert wallet_balance.held_minor == 0  # remaining 20k released, not left held


async def test_capture_more_than_held_is_rejected() -> None:
    wallet = await _create_funded_wallet(100_000_00)

    async with db_session.async_session_factory() as session:
        hold = await create_hold(
            session,
            source_service="payment-service",
            source_id="hold-overcapture-1",
            account_id=wallet.id,
            amount_minor=10_000_00,
            currency="UZS",
            ttl_seconds=900,
        )

    async with db_session.async_session_factory() as session:
        with pytest.raises(CaptureExceedsHoldError):
            await capture_hold(
                session,
                hold.id,
                amount_minor=20_000_00,
                source_service="payment-service",
                source_id="capture-over-1",
            )


async def test_capture_is_idempotent() -> None:
    wallet = await _create_funded_wallet(100_000_00)

    async with db_session.async_session_factory() as session:
        hold = await create_hold(
            session,
            source_service="payment-service",
            source_id="hold-capture-idem",
            account_id=wallet.id,
            amount_minor=10_000_00,
            currency="UZS",
            ttl_seconds=900,
        )

    async with db_session.async_session_factory() as session:
        first = await capture_hold(
            session,
            hold.id,
            amount_minor=10_000_00,
            source_service="payment-service",
            source_id="capture-idem-1",
        )
    async with db_session.async_session_factory() as session:
        second = await capture_hold(
            session,
            hold.id,
            amount_minor=10_000_00,
            source_service="payment-service",
            source_id="capture-idem-1",
        )

    assert first.id == second.id
    wallet_balance = await _balance(wallet.id)
    assert wallet_balance.balance_minor == 90_000_00  # money moved exactly once


async def test_release_hold_returns_funds_without_a_posting() -> None:
    wallet = await _create_funded_wallet(100_000_00)

    async with db_session.async_session_factory() as session:
        hold = await create_hold(
            session,
            source_service="payment-service",
            source_id="hold-release-1",
            account_id=wallet.id,
            amount_minor=25_000_00,
            currency="UZS",
            ttl_seconds=900,
        )

    async with db_session.async_session_factory() as session:
        released = await release_hold(session, hold.id)

    assert released.status == HoldStatus.RELEASED
    balance = await _balance(wallet.id)
    assert balance.balance_minor == 100_000_00  # never moved
    assert balance.held_minor == 0


async def test_releasing_an_already_captured_hold_is_a_no_op() -> None:
    wallet = await _create_funded_wallet(100_000_00)

    async with db_session.async_session_factory() as session:
        hold = await create_hold(
            session,
            source_service="payment-service",
            source_id="hold-release-after-capture",
            account_id=wallet.id,
            amount_minor=10_000_00,
            currency="UZS",
            ttl_seconds=900,
        )
    async with db_session.async_session_factory() as session:
        await capture_hold(
            session,
            hold.id,
            amount_minor=10_000_00,
            source_service="payment-service",
            source_id="capture-then-release",
        )

    async with db_session.async_session_factory() as session:
        result = await release_hold(session, hold.id)

    assert result.status == HoldStatus.CAPTURED  # unchanged, not overwritten
    balance = await _balance(wallet.id)
    assert balance.balance_minor == 90_000_00  # capture's effect is untouched


async def test_capturing_an_expired_hold_is_rejected_and_releases_it() -> None:
    wallet = await _create_funded_wallet(100_000_00)

    async with db_session.async_session_factory() as session:
        hold = await create_hold(
            session,
            source_service="payment-service",
            source_id="hold-expired-1",
            account_id=wallet.id,
            amount_minor=15_000_00,
            currency="UZS",
            ttl_seconds=900,
        )

    # Force it into the past rather than waiting on a real clock.
    async with db_session.async_session_factory() as session:
        stored = await session.get(Hold, hold.id)
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with db_session.async_session_factory() as session:
        with pytest.raises(HoldExpiredError):
            await capture_hold(
                session,
                hold.id,
                amount_minor=15_000_00,
                source_service="payment-service",
                source_id="capture-expired-1",
            )

    balance = await _balance(wallet.id)
    assert balance.held_minor == 0  # lazily released as a side effect


async def test_capturing_an_unknown_hold_is_rejected() -> None:
    async with db_session.async_session_factory() as session:
        with pytest.raises(HoldNotFoundError):
            await capture_hold(
                session,
                uuid.uuid4(),
                amount_minor=1_000,
                source_service="payment-service",
                source_id="capture-unknown-1",
            )


async def test_concurrent_capture_and_release_on_the_same_hold_resolve_to_exactly_one_outcome() -> (
    None
):
    """The row lock in HoldRepository.get_locked serializes this: whichever
    call acquires the lock first fully resolves the hold, and the other
    sees a non-ACTIVE status and takes its no-op/idempotent path — never
    a double-release or a release-after-capture corruption.
    """
    wallet = await _create_funded_wallet(100_000_00)

    async with db_session.async_session_factory() as session:
        hold = await create_hold(
            session,
            source_service="payment-service",
            source_id="hold-race-1",
            account_id=wallet.id,
            amount_minor=40_000_00,
            currency="UZS",
            ttl_seconds=900,
        )

    async def do_capture() -> str:
        async with db_session.async_session_factory() as session:
            try:
                await capture_hold(
                    session,
                    hold.id,
                    amount_minor=40_000_00,
                    source_service="payment-service",
                    source_id="capture-race-1",
                )
                return "captured"
            except Exception:
                return "capture-failed"

    async def do_release() -> str:
        async with db_session.async_session_factory() as session:
            result = await release_hold(session, hold.id)
            return result.status.value.lower()

    results = await asyncio.wait_for(asyncio.gather(do_capture(), do_release()), timeout=10)

    final = await session_get_hold(hold.id)
    assert final.status in (HoldStatus.CAPTURED, HoldStatus.RELEASED)
    balance = await _balance(wallet.id)
    assert balance.held_minor == 0
    assert "captured" in results or "released" in results


async def session_get_hold(hold_id: uuid.UUID) -> Hold:
    async with db_session.async_session_factory() as session:
        hold = await session.get(Hold, hold_id)
        assert hold is not None
        return hold
