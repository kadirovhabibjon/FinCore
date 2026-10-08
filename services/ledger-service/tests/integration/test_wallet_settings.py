"""What an owner can set on their own wallet: a name, which is their
main wallet, and a block that stops money leaving it."""

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.exceptions import WalletBlockedError
from app.db import session as db_session
from app.domain.account import AccountKind, LedgerAccount
from app.domain.posting import EntryDirection, PostingType
from app.main import app
from app.services.holds import capture_hold, create_hold
from app.services.postings import EntryInput, create_posting

pytestmark = pytest.mark.usefixtures("migrated_database")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _open(client: AsyncClient, headers: dict[str, str], currency: str = "UZS") -> dict:
    response = await client.post("/api/v1/wallets", json={"currency": currency}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _system_account_id(kind: AccountKind, currency: str = "UZS") -> uuid.UUID:
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(LedgerAccount).where(
                LedgerAccount.kind == kind, LedgerAccount.currency == currency
            )
        )
        return result.scalar_one().id


async def _move(source: uuid.UUID, destination: uuid.UUID, amount_minor: int) -> None:
    async with db_session.async_session_factory() as session:
        await create_posting(
            session,
            source_service="test",
            source_id=str(uuid.uuid4()),
            type=PostingType.TRANSFER,
            currency="UZS",
            entries=[
                EntryInput(source, EntryDirection.DEBIT, amount_minor),
                EntryInput(destination, EntryDirection.CREDIT, amount_minor),
            ],
        )


async def _fund(wallet_id: str, amount_minor: int) -> None:
    funding = await _system_account_id(AccountKind.EXTERNAL_FUNDING)
    await _move(funding, uuid.UUID(wallet_id), amount_minor)


async def test_the_first_wallet_is_the_main_one_and_later_ones_are_not(issue_access_token) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    async with _client() as client:
        first = await _open(client, headers, "UZS")
        second = await _open(client, headers, "USD")

    assert first["is_primary"] is True
    assert second["is_primary"] is False
    assert first["name"] is None and first["blocked"] is False


async def test_two_first_wallets_opened_at_once_leave_exactly_one_main(issue_access_token) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    async with _client() as client:
        opened = await asyncio.gather(
            client.post("/api/v1/wallets", json={"currency": "UZS"}, headers=headers),
            client.post("/api/v1/wallets", json={"currency": "USD"}, headers=headers),
        )
        listed = await client.get("/api/v1/wallets", headers=headers)

    assert [response.status_code for response in opened] == [201, 201]
    assert sorted(wallet["is_primary"] for wallet in listed.json()) == [False, True]


async def test_choosing_another_main_wallet_moves_the_flag_and_lists_it_first(
    issue_access_token,
) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    async with _client() as client:
        first = await _open(client, headers, "UZS")
        second = await _open(client, headers, "USD")
        chosen = await client.post(f"/api/v1/wallets/{second['id']}/primary", headers=headers)
        again = await client.post(f"/api/v1/wallets/{second['id']}/primary", headers=headers)
        listed = await client.get("/api/v1/wallets", headers=headers)

    assert chosen.status_code == 200 and chosen.json()["is_primary"] is True
    assert again.status_code == 200
    assert [(wallet["id"], wallet["is_primary"]) for wallet in listed.json()] == [
        (second["id"], True),
        (first["id"], False),
    ]


async def test_the_main_wallet_can_be_moved_back_and_forth(issue_access_token) -> None:
    """Whichever row the database happens to reach first: neither
    direction may leave two main wallets, even for a moment."""
    headers = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    async with _client() as client:
        first = await _open(client, headers, "UZS")
        second = await _open(client, headers, "USD")
        for chosen in (second, first, second, first):
            response = await client.post(
                f"/api/v1/wallets/{chosen['id']}/primary", headers=headers
            )
            assert response.status_code == 200, response.text
            listed = (await client.get("/api/v1/wallets", headers=headers)).json()
            assert [wallet["id"] for wallet in listed if wallet["is_primary"]] == [chosen["id"]]


async def test_choosing_two_main_wallets_at_once_leaves_exactly_one(issue_access_token) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    async with _client() as client:
        first = await _open(client, headers, "UZS")
        second = await _open(client, headers, "USD")
        for _ in range(5):
            responses = await asyncio.gather(
                client.post(f"/api/v1/wallets/{first['id']}/primary", headers=headers),
                client.post(f"/api/v1/wallets/{second['id']}/primary", headers=headers),
            )
            assert [response.status_code for response in responses] == [200, 200]
            listed = (await client.get("/api/v1/wallets", headers=headers)).json()
            assert sorted(wallet["is_primary"] for wallet in listed) == [False, True]


async def test_a_wallet_can_be_named_renamed_and_unnamed(issue_access_token) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    async with _client() as client:
        wallet = await _open(client, headers)
        url = f"/api/v1/wallets/{wallet['id']}"
        named = await client.patch(url, json={"name": "  Salary   card "}, headers=headers)
        blank = await client.patch(url, json={"name": "   "}, headers=headers)
        too_long = await client.patch(url, json={"name": "x" * 41}, headers=headers)
        fetched = await client.get(url, headers=headers)

    assert named.status_code == 200 and named.json()["name"] == "Salary card"
    assert blank.status_code == 200 and blank.json()["name"] is None
    assert too_long.status_code == 422
    assert fetched.json()["name"] is None


@pytest.mark.parametrize("action", ["patch", "primary", "block", "unblock"])
async def test_someone_elses_wallet_cannot_be_changed(issue_access_token, action: str) -> None:
    owner = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    stranger = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    async with _client() as client:
        wallet = await _open(client, owner)
        url = f"/api/v1/wallets/{wallet['id']}"
        if action == "patch":
            response = await client.patch(url, json={"name": "Mine now"}, headers=stranger)
        else:
            response = await client.post(f"{url}/{action}", headers=stranger)
        unchanged = await client.get(url, headers=owner)

    assert response.status_code == 404
    assert response.json()["title"] == "Wallet Not Found"
    assert unchanged.json() == wallet


async def test_a_blocked_wallet_receives_money_but_none_leaves(issue_access_token) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    other = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    async with _client() as client:
        wallet = await _open(client, headers)
        friend = await _open(client, other)
        await _fund(wallet["id"], 50_000)
        await _fund(friend["id"], 50_000)
        blocked = await client.post(f"/api/v1/wallets/{wallet['id']}/block", headers=headers)
        again = await client.post(f"/api/v1/wallets/{wallet['id']}/block", headers=headers)
        mine, theirs = uuid.UUID(wallet["id"]), uuid.UUID(friend["id"])

        with pytest.raises(WalletBlockedError):
            await _move(mine, theirs, 10_000)
        async with db_session.async_session_factory() as session:
            with pytest.raises(WalletBlockedError):
                await create_hold(
                    session,
                    source_service="test",
                    source_id=str(uuid.uuid4()),
                    account_id=mine,
                    amount_minor=10_000,
                    currency="UZS",
                    ttl_seconds=600,
                )
        await _move(theirs, mine, 20_000)  # money still arrives
        after_block = await client.get(f"/api/v1/wallets/{wallet['id']}", headers=headers)

        unblocked = await client.post(f"/api/v1/wallets/{wallet['id']}/unblock", headers=headers)
        await _move(mine, theirs, 10_000)
        after_unblock = await client.get(f"/api/v1/wallets/{wallet['id']}", headers=headers)

    assert blocked.json()["blocked"] is True and again.json()["blocked"] is True
    assert blocked.json()["status"] == "ACTIVE"  # FinCore's own status is untouched
    assert after_block.json()["balance_minor"] == 70_000
    assert after_block.json()["held_minor"] == 0
    assert unblocked.json()["blocked"] is False
    assert after_unblock.json()["balance_minor"] == 60_000


async def test_a_payment_reserved_before_the_block_still_completes(issue_access_token) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    async with _client() as client:
        wallet = await _open(client, headers)
        await _fund(wallet["id"], 50_000)
        async with db_session.async_session_factory() as session:
            hold = await create_hold(
                session,
                source_service="test",
                source_id=str(uuid.uuid4()),
                account_id=uuid.UUID(wallet["id"]),
                amount_minor=30_000,
                currency="UZS",
                ttl_seconds=600,
            )
        await client.post(f"/api/v1/wallets/{wallet['id']}/block", headers=headers)
        async with db_session.async_session_factory() as session:
            await capture_hold(
                session,
                hold_id=hold.id,
                amount_minor=30_000,
                source_service="test",
                source_id=str(uuid.uuid4()),
            )
        after = await client.get(f"/api/v1/wallets/{wallet['id']}", headers=headers)

    assert after.json()["balance_minor"] == 20_000
    assert after.json()["held_minor"] == 0
