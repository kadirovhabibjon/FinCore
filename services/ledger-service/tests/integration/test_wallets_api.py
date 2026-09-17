import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import session as db_session
from app.domain.account import AccountKind, LedgerAccount
from app.domain.posting import EntryDirection, PostingType
from app.main import app
from app.services.postings import EntryInput, create_posting

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_open_wallet_requires_authentication() -> None:
    async with await _client() as client:
        response = await client.post("/api/v1/wallets", json={"currency": "UZS"})

    assert response.status_code == 401


async def test_open_wallet_creates_a_zero_balance_wallet(issue_access_token) -> None:
    user_id = uuid.uuid4()
    token = issue_access_token(user_id)

    async with await _client() as client:
        response = await client.post(
            "/api/v1/wallets",
            json={"currency": "UZS"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["currency"] == "UZS"
    assert body["balance_minor"] == 0
    assert body["held_minor"] == 0
    assert body["status"] == "ACTIVE"


async def test_opening_a_second_wallet_in_the_same_currency_is_rejected(issue_access_token) -> None:
    user_id = uuid.uuid4()
    token = issue_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with await _client() as client:
        first = await client.post("/api/v1/wallets", json={"currency": "UZS"}, headers=headers)
        second = await client.post("/api/v1/wallets", json={"currency": "UZS"}, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["title"] == "Wallet Already Exists"


async def test_a_user_can_open_wallets_in_different_currencies(issue_access_token) -> None:
    user_id = uuid.uuid4()
    token = issue_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with await _client() as client:
        uzs = await client.post("/api/v1/wallets", json={"currency": "UZS"}, headers=headers)
        usd = await client.post("/api/v1/wallets", json={"currency": "USD"}, headers=headers)

    assert uzs.status_code == 201
    assert usd.status_code == 201


async def test_opening_a_wallet_in_an_unsupported_currency_is_rejected(issue_access_token) -> None:
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.post(
            "/api/v1/wallets",
            json={"currency": "EUR"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422
    assert response.json()["title"] == "Unsupported Currency"


async def test_list_wallets_only_returns_the_callers_own_wallets(issue_access_token) -> None:
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    token = issue_access_token(user_id)
    other_token = issue_access_token(other_user_id)

    async with await _client() as client:
        await client.post(
            "/api/v1/wallets",
            json={"currency": "UZS"},
            headers={"Authorization": f"Bearer {token}"},
        )
        await client.post(
            "/api/v1/wallets",
            json={"currency": "UZS"},
            headers={"Authorization": f"Bearer {other_token}"},
        )

        response = await client.get(
            "/api/v1/wallets", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    wallets = response.json()
    assert len(wallets) == 1


async def test_getting_someone_elses_wallet_returns_not_found(issue_access_token) -> None:
    owner_token = issue_access_token(uuid.uuid4())
    intruder_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        created = await client.post(
            "/api/v1/wallets",
            json={"currency": "UZS"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        wallet_id = created.json()["id"]

        response = await client.get(
            f"/api/v1/wallets/{wallet_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

    assert response.status_code == 404
    assert response.json()["title"] == "Wallet Not Found"


async def test_wallet_entries_reflect_postings_that_touched_it(issue_access_token) -> None:
    user_id = uuid.uuid4()
    token = issue_access_token(user_id)

    async with await _client() as client:
        created = await client.post(
            "/api/v1/wallets",
            json={"currency": "UZS"},
            headers={"Authorization": f"Bearer {token}"},
        )
        wallet_id = created.json()["id"]

        async with db_session.async_session_factory() as session:
            result = await session.execute(
                select(LedgerAccount).where(
                    LedgerAccount.kind == AccountKind.EXTERNAL_FUNDING,
                    LedgerAccount.currency == "UZS",
                )
            )
            funding_id = result.scalar_one().id

        async with db_session.async_session_factory() as session:
            await create_posting(
                session,
                source_service="test",
                source_id="wallet-entries-deposit",
                type=PostingType.DEPOSIT,
                currency="UZS",
                entries=[
                    EntryInput(funding_id, EntryDirection.DEBIT, 25_000_00),
                    EntryInput(uuid.UUID(wallet_id), EntryDirection.CREDIT, 25_000_00),
                ],
            )

        response = await client.get(
            f"/api/v1/wallets/{wallet_id}/entries",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 1
    assert entries[0]["direction"] == "CREDIT"
    assert entries[0]["amount_minor"] == 25_000_00


async def test_wallet_entries_requires_ownership(issue_access_token) -> None:
    owner_token = issue_access_token(uuid.uuid4())
    intruder_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        created = await client.post(
            "/api/v1/wallets",
            json={"currency": "UZS"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        wallet_id = created.json()["id"]

        response = await client.get(
            f"/api/v1/wallets/{wallet_id}/entries",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

    assert response.status_code == 404
