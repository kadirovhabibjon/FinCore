"""GET /api/v1/transfers/recipient?phone=...&currency=...: a phone
number typed by the sender becomes that person's wallet in the currency
being sent, and a name to confirm."""

import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fincore_common import generate_card_number
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.integration.test_recipient_lookup import _install

_PHONE = "+998901234567"
_OWNER = uuid.uuid4()
_WALLET = uuid.uuid4()
_CARD = generate_card_number()


def _identity_app(
    *, status: str = "ACTIVE", known: bool = True, code: int = 200, seen: list | None = None
) -> FastAPI:
    fake = FastAPI()

    @fake.get("/internal/v1/users/by-phone")
    async def _by_phone(phone: str) -> JSONResponse:
        if seen is not None:
            seen.append(phone)
        if code != 200:
            return JSONResponse({"title": "x", "status": code}, status_code=code)
        if "x" in phone:
            return JSONResponse(
                {"title": "Invalid Phone Number", "status": 422, "detail": "enter a phone number"},
                status_code=422,
            )
        if not known:
            return JSONResponse({"title": "User Not Found", "status": 404}, status_code=404)
        return JSONResponse(
            {"id": str(_OWNER), "first_name": "Aziza", "last_name": "Karimova", "status": status}
        )

    return fake


def _ledger_app(
    *, status: str = "ACTIVE", has_wallet: bool = True, code: int = 200, seen: list | None = None
) -> FastAPI:
    fake = FastAPI()

    @fake.get("/internal/v1/accounts/wallet-of/{user_id}")
    async def _wallet_of(user_id: str, currency: str) -> JSONResponse:
        if seen is not None:
            seen.append((user_id, currency))
        if code != 200:
            return JSONResponse({"title": "x", "status": code}, status_code=code)
        if not has_wallet:
            return JSONResponse({"title": "Wallet Not Found", "status": 404}, status_code=404)
        return JSONResponse(
            {
                "id": str(_WALLET),
                "owner_user_id": user_id,
                "card_number": _CARD,
                "currency": currency,
                "status": status,
            }
        )

    return fake


def _use(monkeypatch: pytest.MonkeyPatch, ledger_app: FastAPI, identity_app: FastAPI) -> None:
    _install(monkeypatch, ASGITransport(app=ledger_app), ASGITransport(app=identity_app))


async def _lookup(token: str | None, **params: str) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/api/v1/transfers/recipient", params=params, headers=headers)


async def test_a_phone_number_leads_to_its_owners_wallet_in_the_currency_sent(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    asked_identity: list = []
    asked_ledger: list = []
    _use(monkeypatch, _ledger_app(seen=asked_ledger), _identity_app(seen=asked_identity))

    response = await _lookup(
        issue_access_token(uuid.uuid4()), phone="90 123-45-67", currency="USD"
    )

    assert response.status_code == 200
    assert response.json() == {
        "wallet_id": str(_WALLET),
        "currency": "USD",
        "display_name": "Aziza K.",
        "own": False,
        "card_last4": _CARD[-4:],
    }
    # The number goes to identity-service as typed: it owns the stored form.
    assert asked_identity == ["90 123-45-67"]
    assert asked_ledger == [(str(_OWNER), "USD")]


async def test_says_when_the_phone_number_is_the_callers_own(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _use(monkeypatch, _ledger_app(), _identity_app())

    response = await _lookup(issue_access_token(_OWNER), phone=_PHONE, currency="UZS")

    assert response.json()["own"] is True


@pytest.mark.parametrize(
    ("ledger_options", "identity_options"),
    [
        ({}, {"known": False}),
        ({}, {"status": "BLOCKED"}),
        ({"has_wallet": False}, {}),
        ({"status": "FROZEN"}, {}),
    ],
    ids=["unknown number", "account not active", "no wallet in the currency", "wallet frozen"],
)
async def test_every_reason_a_phone_number_cannot_receive_looks_the_same(
    monkeypatch: pytest.MonkeyPatch,
    issue_access_token,
    ledger_options: dict,
    identity_options: dict,
) -> None:
    _use(monkeypatch, _ledger_app(**ledger_options), _identity_app(**identity_options))

    response = await _lookup(issue_access_token(uuid.uuid4()), phone=_PHONE, currency="UZS")

    assert response.status_code == 404
    assert response.json()["title"] == "Recipient Not Found"
    assert response.json()["detail"] == "nobody can receive UZS at this phone number"


async def test_a_malformed_phone_number_is_a_validation_error_not_a_missing_person(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    asked_ledger: list = []
    _use(monkeypatch, _ledger_app(seen=asked_ledger), _identity_app())

    response = await _lookup(issue_access_token(uuid.uuid4()), phone="12x45x", currency="UZS")

    assert response.status_code == 422
    assert response.json()["title"] == "Invalid Phone Number"
    assert asked_ledger == []


@pytest.mark.parametrize(
    ("ledger_options", "identity_options"),
    [({}, {"code": 500}), ({}, {"code": 403}), ({"code": 500}, {})],
    ids=["identity down", "identity refuses the token", "ledger down"],
)
async def test_a_service_that_cannot_answer_is_not_reported_as_nobody(
    monkeypatch: pytest.MonkeyPatch,
    issue_access_token,
    ledger_options: dict,
    identity_options: dict,
) -> None:
    _use(monkeypatch, _ledger_app(**ledger_options), _identity_app(**identity_options))

    response = await _lookup(issue_access_token(uuid.uuid4()), phone=_PHONE, currency="UZS")

    assert response.status_code == 503
    assert response.json()["title"] == "Recipient Lookup Unavailable"


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"phone": _PHONE},
        {"currency": "UZS"},
        {"phone": _PHONE, "currency": "UZS", "card_number": _CARD},
    ],
    ids=["nothing", "phone without currency", "currency alone", "both a card and a phone"],
)
async def test_a_lookup_is_by_card_or_by_phone_and_currency(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, params: dict
) -> None:
    _use(monkeypatch, _ledger_app(), _identity_app())

    response = await _lookup(issue_access_token(uuid.uuid4()), **params)

    assert response.status_code == 422
    assert response.json()["title"] == "Invalid Recipient Query"


async def test_needs_a_signed_in_customer(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _ledger_app(), _identity_app())

    assert (await _lookup(None, phone=_PHONE, currency="UZS")).status_code == 401
