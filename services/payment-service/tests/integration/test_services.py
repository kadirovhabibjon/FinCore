"""Paying service providers (app/services/billers.py): the catalogue,
and a payment to one - an ordinary payment that also records which
provider and which account it was for."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.exceptions import InvalidServiceAccountError
from app.db import session as db_session
from app.domain.merchant import Merchant, MerchantStatus
from app.domain.outbox import OutboxEvent
from app.services import billers
from tests.integration import test_payment_saga as payments

pytestmark = pytest.mark.usefixtures("migrated_database")

_WALLET = uuid.uuid4()


def _wire(monkeypatch: pytest.MonkeyPatch, *, wallet_currency: str = "UZS") -> None:
    payments._wire_ledger(monkeypatch, payments._ledger_app(wallet_currency=wallet_currency))
    payments._wire_fraud(monkeypatch, "ALLOW")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _pay(
    client: AsyncClient,
    token: str,
    code: str,
    *,
    account: str,
    amount: str = "10000.00",
    key: str | None = None,
) -> dict:
    response = await client.post(
        f"/api/v1/services/{code}/payments",
        json={"source_wallet_id": str(_WALLET), "account": account, "amount": amount},
        headers={**_auth(token), "Idempotency-Key": key or str(uuid.uuid4())},
    )
    return {"status_code": response.status_code, **response.json()}


async def test_every_provider_in_the_catalogue_has_its_merchant() -> None:
    """A provider added to the catalogue without its migration would
    fail every payment on the foreign key: caught here instead."""
    async with db_session.async_session_factory() as session:
        rows = (
            await session.execute(
                select(Merchant).where(Merchant.owner_user_id == billers.SYSTEM_OWNER_ID)
            )
        ).scalars().all()

    assert {(row.id, row.name) for row in rows} == {
        (biller.merchant_id, biller.name) for biller in billers.CATALOG
    }
    assert all(row.status == MerchantStatus.ACTIVE for row in rows)
    assert len({biller.code for biller in billers.CATALOG}) == len(billers.CATALOG)


async def test_the_catalogue_lists_what_can_be_paid(issue_access_token) -> None:
    async with await payments._client() as client:
        token = issue_access_token(uuid.uuid4())
        listed = await client.get("/api/v1/services", headers=_auth(token))
        anonymous = await client.get("/api/v1/services")

    assert anonymous.status_code == 401
    assert listed.status_code == 200
    services = listed.json()
    assert [service["code"] for service in services] == [b.code for b in billers.CATALOG]
    assert services[0] == {
        "code": "beeline",
        "category": "MOBILE",
        "name": "Beeline",
        "account_kind": "PHONE",
        "currency": "UZS",
        "min_amount_minor": 100_000,
        "max_amount_minor": 500_000_000,
    }
    assert {service["category"] for service in services} == {
        "MOBILE",
        "INTERNET",
        "UTILITIES",
        "TV",
    }


async def test_paying_a_provider_is_a_payment_recorded_with_its_account(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire(monkeypatch)
    token = issue_access_token(uuid.uuid4())

    async with await payments._client() as client:
        paid = await _pay(client, token, "beeline", account="90 123-45-67", amount="25000")
        fetched = await client.get(f"/api/v1/payments/{paid['id']}", headers=_auth(token))
        history = await client.get("/api/v1/transactions", headers=_auth(token))

    beeline = billers.find("beeline")
    assert beeline is not None
    assert paid["status_code"] == 201
    assert paid["status"] == "SUCCESS"
    assert paid["amount_minor"] == 2_500_000 and paid["currency"] == "UZS"
    assert paid["merchant_id"] == str(beeline.merchant_id)
    assert (paid["service_code"], paid["service_account"]) == ("beeline", "+998901234567")
    assert paid["description"] == "+998901234567"
    assert fetched.json()["service_account"] == "+998901234567"
    assert [item["id"] for item in history.json()] == [paid["id"]]

    async with db_session.async_session_factory() as session:
        events = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == paid["id"])
            )
        ).scalars().all()
    assert [event.event_type for event in events] == ["payment.completed"]
    # The payer is told who was paid; there is no owner to tell it was received.
    assert events[0].payload["merchant_name"] == "Beeline"
    assert events[0].payload["merchant_owner_user_id"] is None


async def test_a_retry_with_the_same_key_pays_once(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire(monkeypatch)
    token, key = issue_access_token(uuid.uuid4()), str(uuid.uuid4())

    async with await payments._client() as client:
        first = await _pay(client, token, "electricity", account="1234567", key=key)
        again = await _pay(client, token, "electricity", account="1234567", key=key)
        other = await _pay(client, token, "electricity", account="7654321", key=key)
        history = await client.get("/api/v1/transactions", headers=_auth(token))

    assert again == first
    assert other["status_code"] == 422 and other["title"] == "Idempotency Key Conflict"
    assert len(history.json()) == 1


@pytest.mark.parametrize(
    ("code", "account", "recorded"),
    [
        ("ucell", "+998 93 555 44 33", "+998935554433"),
        ("ucell", "998935554433", "+998935554433"),
        ("ucell", "935554433", "+998935554433"),
        ("uzonline", "aziza_k-01", "aziza_k-01"),
        ("natural-gas", "0012 3456-78", "0012345678"),
        ("uzdigital-tv", "123456", "123456"),
    ],
)
def test_an_account_is_recorded_in_one_form(code: str, account: str, recorded: str) -> None:
    biller = billers.find(code)
    assert biller is not None
    assert billers.clean_account(biller, account) == recorded


@pytest.mark.parametrize(
    ("code", "account"),
    [
        ("beeline", "12345"),
        ("beeline", "+7 912 345 67 89"),
        ("beeline", "90123456a"),
        ("uzonline", "ab"),
        ("uzonline", "has space"),
        ("uzonline", "x" * 33),
        ("electricity", "12345"),
        ("electricity", "123456789012345"),
        ("electricity", "12345a7"),
        ("electricity", "١٢٣٤٥٦٧"),
    ],
)
def test_an_account_of_the_wrong_shape_is_refused(code: str, account: str) -> None:
    biller = billers.find(code)
    assert biller is not None
    with pytest.raises(InvalidServiceAccountError):
        billers.clean_account(biller, account)


@pytest.mark.parametrize(
    ("code", "account", "amount", "status_code", "title"),
    [
        ("no-such-provider", "901234567", "10000", 404, "Service Not Found"),
        ("beeline", "12345", "10000", 422, "Invalid Service Account"),
        ("beeline", "901234567", "999.99", 422, "Amount Out Of Range"),
        ("beeline", "901234567", "5000000.01", 422, "Amount Out Of Range"),
        ("beeline", "901234567", "0", 422, "Invalid Amount"),
        ("beeline", "901234567", "ten", 422, "Invalid Amount"),
    ],
)
async def test_a_bad_request_is_refused_before_anything_is_created(
    monkeypatch: pytest.MonkeyPatch,
    issue_access_token,
    code: str,
    account: str,
    amount: str,
    status_code: int,
    title: str,
) -> None:
    _wire(monkeypatch)
    token = issue_access_token(uuid.uuid4())

    async with await payments._client() as client:
        refused = await _pay(client, token, code, account=account, amount=amount)
        history = await client.get("/api/v1/transactions", headers=_auth(token))

    assert (refused["status_code"], refused["title"]) == (status_code, title)
    assert history.json() == []


async def test_the_smallest_and_largest_amounts_are_accepted(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire(monkeypatch)
    token = issue_access_token(uuid.uuid4())

    async with await payments._client() as client:
        least = await _pay(client, token, "comnet", account="user1", amount="1000")
        most = await _pay(client, token, "comnet", account="user1", amount="5000000.00")

    assert least["status"] == most["status"] == "SUCCESS"


async def test_providers_are_paid_in_their_own_currency(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire(monkeypatch, wallet_currency="USD")

    async with await payments._client() as client:
        token = issue_access_token(uuid.uuid4())
        refused = await _pay(client, token, "beeline", account="901234567")

    assert refused["status_code"] == 422 and refused["title"] == "Currency Mismatch"


async def test_a_wallet_that_is_not_the_callers_cannot_pay(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    payments._wire_ledger(monkeypatch, payments._ledger_app(wallet_found=False))
    payments._wire_fraud(monkeypatch, "ALLOW")

    async with await payments._client() as client:
        token = issue_access_token(uuid.uuid4())
        refused = await _pay(client, token, "beeline", account="901234567")
        anonymous = await client.post(
            "/api/v1/services/beeline/payments",
            json={"source_wallet_id": str(_WALLET), "account": "901234567", "amount": "10000"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )

    assert refused["status_code"] == 404 and refused["title"] == "Wallet Not Found"
    assert anonymous.status_code == 401


async def test_a_providers_merchant_cannot_be_paid_as_an_ordinary_merchant(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    """Without the account the payment is for, it would be money sent
    to a provider for nobody."""
    _wire(monkeypatch)
    beeline = billers.find("beeline")
    assert beeline is not None

    async with await payments._client() as client:
        response = await payments._post_payment(
            client, issue_access_token(uuid.uuid4()), beeline.merchant_id, amount="10000.00"
        )

    assert response.status_code == 404
    assert response.json()["title"] == "Merchant Not Found"


async def test_a_service_payment_counts_towards_the_daily_limit(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire(monkeypatch)
    token = issue_access_token(uuid.uuid4())

    async with await payments._client() as client:
        await client.put(
            f"/api/v1/limits/{_WALLET}", json={"daily_limit": "15000.00"}, headers=_auth(token)
        )
        first = await _pay(client, token, "beeline", account="901234567", amount="10000")
        second = await _pay(client, token, "beeline", account="901234567", amount="10000")

    assert first["status"] == "SUCCESS"
    assert second["status"] == "FAILED" and second["failure_reason"] == "Daily Limit Exceeded"
