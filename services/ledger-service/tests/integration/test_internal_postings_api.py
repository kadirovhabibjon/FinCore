import uuid

import pytest
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
