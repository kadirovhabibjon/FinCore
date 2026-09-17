import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from app.domain.account import AccountKind, LedgerAccount

pytestmark = pytest.mark.usefixtures("migrated_database")


async def test_system_accounts_are_seeded_by_migration() -> None:
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(LedgerAccount).where(LedgerAccount.kind == AccountKind.FEES)
        )
        fee_accounts = result.scalars().all()

    assert {account.currency for account in fee_accounts} == {"UZS", "USD"}
    assert all(account.owner_user_id is None for account in fee_accounts)


async def test_creating_a_wallet_succeeds() -> None:
    user_id = uuid.uuid4()

    async with db_session.async_session_factory() as session:
        session.add(
            LedgerAccount(kind=AccountKind.USER_WALLET, owner_user_id=user_id, currency="UZS")
        )
        await session.commit()

    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(LedgerAccount).where(LedgerAccount.owner_user_id == user_id)
        )
        wallet = result.scalar_one()

    assert wallet.currency == "UZS"
    assert wallet.kind == AccountKind.USER_WALLET


async def test_a_user_cannot_have_two_wallets_in_the_same_currency() -> None:
    user_id = uuid.uuid4()

    async with db_session.async_session_factory() as session:
        session.add(
            LedgerAccount(kind=AccountKind.USER_WALLET, owner_user_id=user_id, currency="UZS")
        )
        await session.commit()

    async with db_session.async_session_factory() as session:
        session.add(
            LedgerAccount(kind=AccountKind.USER_WALLET, owner_user_id=user_id, currency="UZS")
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_a_user_can_have_wallets_in_different_currencies() -> None:
    user_id = uuid.uuid4()

    async with db_session.async_session_factory() as session:
        session.add(
            LedgerAccount(kind=AccountKind.USER_WALLET, owner_user_id=user_id, currency="UZS")
        )
        session.add(
            LedgerAccount(kind=AccountKind.USER_WALLET, owner_user_id=user_id, currency="USD")
        )
        await session.commit()

    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(LedgerAccount).where(LedgerAccount.owner_user_id == user_id)
        )
        wallets = result.scalars().all()

    assert {w.currency for w in wallets} == {"UZS", "USD"}


async def test_cannot_create_a_second_system_account_of_the_same_kind_and_currency() -> None:
    # FEES/UZS already exists from the migration seed.
    async with db_session.async_session_factory() as session:
        session.add(LedgerAccount(kind=AccountKind.FEES, owner_user_id=None, currency="UZS"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_a_system_account_cannot_have_an_owner() -> None:
    async with db_session.async_session_factory() as session:
        session.add(
            LedgerAccount(kind=AccountKind.SUSPENSE, owner_user_id=uuid.uuid4(), currency="EUR")
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_a_user_wallet_must_have_an_owner() -> None:
    async with db_session.async_session_factory() as session:
        session.add(
            LedgerAccount(kind=AccountKind.USER_WALLET, owner_user_id=None, currency="UZS")
        )
        with pytest.raises(IntegrityError):
            await session.commit()
