import uuid

import pytest
from fincore_common import generate_card_number
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.db import session as db_session
from app.domain.account import AccountKind, LedgerAccount
from app.domain.balance import AccountBalance
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_HEADERS = {"X-Internal-Token": settings.internal_service_token}


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _create_wallet(currency: str = "UZS") -> LedgerAccount:
    async with db_session.async_session_factory() as session:
        account = LedgerAccount(
            kind=AccountKind.USER_WALLET,
            owner_user_id=uuid.uuid4(),
            currency=currency,
            card_number=generate_card_number(),
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


async def test_posting_endpoint_requires_the_internal_token_header() -> None:
    async with await _client() as client:
        response = await client.post("/internal/v1/postings", json={})

    assert response.status_code == 422  # FastAPI's required-header validation


async def test_posting_endpoint_rejects_the_wrong_internal_token() -> None:
    async with await _client() as client:
        response = await client.post(
            "/internal/v1/postings", json={}, headers={"X-Internal-Token": "wrong"}
        )

    assert response.status_code == 403
    assert response.json()["title"] == "Invalid Internal Service Token"


async def test_create_posting_via_internal_api_moves_money() -> None:
    wallet = await _create_wallet()
    funding_id = await _system_account_id(AccountKind.EXTERNAL_FUNDING)

    async with await _client() as client:
        response = await client.post(
            "/internal/v1/postings",
            json={
                "source_service": "payment-service",
                "source_id": "internal-dep-1",
                "type": "DEPOSIT",
                "currency": "UZS",
                "entries": [
                    {
                        "account_id": str(funding_id),
                        "direction": "DEBIT",
                        "amount_minor": 10_000_00,
                    },
                    {
                        "account_id": str(wallet.id),
                        "direction": "CREDIT",
                        "amount_minor": 10_000_00,
                    },
                ],
            },
            headers=_HEADERS,
        )

    assert response.status_code == 201
    body = response.json()
    assert body["source_service"] == "payment-service"
    assert body["type"] == "DEPOSIT"

    async with db_session.async_session_factory() as session:
        balance = await session.get(AccountBalance, wallet.id)
        assert balance is not None
        assert balance.balance_minor == 10_000_00


async def test_create_posting_is_idempotent_via_the_api() -> None:
    wallet = await _create_wallet()
    funding_id = await _system_account_id(AccountKind.EXTERNAL_FUNDING)
    payload = {
        "source_service": "payment-service",
        "source_id": "internal-dep-idem",
        "type": "DEPOSIT",
        "currency": "UZS",
        "entries": [
            {"account_id": str(funding_id), "direction": "DEBIT", "amount_minor": 5_000_00},
            {"account_id": str(wallet.id), "direction": "CREDIT", "amount_minor": 5_000_00},
        ],
    }

    async with await _client() as client:
        first = await client.post("/internal/v1/postings", json=payload, headers=_HEADERS)
        second = await client.post("/internal/v1/postings", json=payload, headers=_HEADERS)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_get_posting_by_source_returns_it() -> None:
    wallet = await _create_wallet()
    funding_id = await _system_account_id(AccountKind.EXTERNAL_FUNDING)

    async with await _client() as client:
        created = await client.post(
            "/internal/v1/postings",
            json={
                "source_service": "payment-service",
                "source_id": "internal-dep-lookup",
                "type": "DEPOSIT",
                "currency": "UZS",
                "entries": [
                    {"account_id": str(funding_id), "direction": "DEBIT", "amount_minor": 1_000},
                    {"account_id": str(wallet.id), "direction": "CREDIT", "amount_minor": 1_000},
                ],
            },
            headers=_HEADERS,
        )
        posting_id = created.json()["id"]

        response = await client.get(
            "/internal/v1/postings/internal-dep-lookup",
            params={"source_service": "payment-service", "type": "DEPOSIT"},
            headers=_HEADERS,
        )

    assert response.status_code == 200
    assert response.json()["id"] == posting_id


async def test_get_unknown_posting_returns_404() -> None:
    async with await _client() as client:
        response = await client.get(
            "/internal/v1/postings/does-not-exist",
            params={"source_service": "payment-service", "type": "DEPOSIT"},
            headers=_HEADERS,
        )

    assert response.status_code == 404
    assert response.json()["title"] == "Posting Not Found"


async def test_an_exchange_is_two_balanced_postings_against_the_exchange_accounts() -> None:
    """Selling 1,200,000.00 UZS for 100.00 USD: the UZS leg moves the
    customer's UZS to FinCore's UZS position, the USD leg moves USD from
    FinCore's USD position to the customer. Each posting balances in its
    own currency; FinCore's positions end up +UZS and -USD."""
    uzs_wallet = await _create_wallet("UZS")
    usd_wallet = await _create_wallet("USD")
    funding = await _system_account_id(AccountKind.EXTERNAL_FUNDING)
    uzs_position = await _system_account_id(AccountKind.EXCHANGE, "UZS")
    usd_position = await _system_account_id(AccountKind.EXCHANGE, "USD")

    def posting(
        source_id: str, type_: str, currency: str, debit: uuid.UUID, credit: uuid.UUID, amount: int
    ) -> dict:
        return {
            "source_service": "test",
            "source_id": source_id,
            "type": type_,
            "currency": currency,
            "entries": [
                {"account_id": str(debit), "direction": "DEBIT", "amount_minor": amount},
                {"account_id": str(credit), "direction": "CREDIT", "amount_minor": amount},
            ],
        }

    exchange_id = uuid.uuid4().hex
    async with await _client() as client:
        funded = await client.post(
            "/internal/v1/postings",
            json=posting(
                f"fund-{exchange_id}", "DEPOSIT", "UZS", funding, uzs_wallet.id, 2_000_000_00
            ),
            headers=_HEADERS,
        )
        sell = await client.post(
            "/internal/v1/postings",
            json=posting(
                f"{exchange_id}:sell", "EXCHANGE", "UZS", uzs_wallet.id, uzs_position, 1_200_000_00
            ),
            headers=_HEADERS,
        )
        buy = await client.post(
            "/internal/v1/postings",
            json=posting(
                f"{exchange_id}:buy", "EXCHANGE", "USD", usd_position, usd_wallet.id, 100_00
            ),
            headers=_HEADERS,
        )
        # The customer cannot sell what they do not have.
        oversell = await client.post(
            "/internal/v1/postings",
            json=posting(
                f"{exchange_id}:again", "EXCHANGE", "UZS", uzs_wallet.id, uzs_position, 900_000_00
            ),
            headers=_HEADERS,
        )
        found = await client.get(
            "/internal/v1/accounts/system",
            params={"kind": "EXCHANGE", "currency": "USD"},
            headers=_HEADERS,
        )

    assert (funded.status_code, sell.status_code, buy.status_code) == (201, 201, 201)
    assert oversell.status_code == 409 and oversell.json()["title"] == "Insufficient Funds"
    assert found.status_code == 200 and found.json()["id"] == str(usd_position)

    async with db_session.async_session_factory() as session:
        balances = {
            account: (await session.get(AccountBalance, account)).balance_minor
            for account in (uzs_wallet.id, usd_wallet.id, uzs_position, usd_position)
        }
    assert balances[uzs_wallet.id] == 800_000_00
    assert balances[usd_wallet.id] == 100_00
    # Shared across the test database, so compared as "moved by", not "equals".
    assert balances[uzs_position] >= 1_200_000_00
    assert balances[usd_position] <= -100_00
