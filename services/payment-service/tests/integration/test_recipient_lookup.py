"""GET /api/v1/transfers/recipient: a card number typed by the sender
becomes the wallet to send to and a name to confirm."""

import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fincore_common import generate_card_number
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.services import identity, ledger
from app.services.recipients import display_name

_CARD = generate_card_number()
_WALLET = uuid.uuid4()
_OWNER = uuid.uuid4()


def _ledger_app(*, status: str = "ACTIVE", found: bool = True, seen: list | None = None) -> FastAPI:
    fake = FastAPI()

    @fake.get("/internal/v1/accounts/wallet-by-card")
    async def _by_card(card_number: str) -> JSONResponse:
        if seen is not None:
            seen.append(card_number)
        if not found or card_number != _CARD:
            return JSONResponse({"title": "Wallet Not Found", "status": 404}, status_code=404)
        return JSONResponse(
            {
                "id": str(_WALLET),
                "owner_user_id": str(_OWNER),
                "currency": "UZS",
                "status": status,
            }
        )

    return fake


def _identity_app(*, status: str = "ACTIVE", code: int = 200) -> FastAPI:
    fake = FastAPI()

    @fake.get("/internal/v1/users/{user_id}")
    async def _user(user_id: str) -> JSONResponse:
        if code != 200:
            return JSONResponse({"title": "x", "status": code}, status_code=code)
        return JSONResponse(
            {"id": user_id, "first_name": "Aziza", "last_name": "Karimova", "status": status}
        )

    return fake


def _install(
    monkeypatch: pytest.MonkeyPatch,
    ledger_transport: httpx.AsyncBaseTransport,
    identity_transport: httpx.AsyncBaseTransport,
) -> None:
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://ledger",
            internal_token=settings.internal_service_token,
            timeout_seconds=5.0,
            transport=ledger_transport,
        ),
    )
    monkeypatch.setattr(
        identity,
        "identity_client",
        identity.IdentityClient(
            base_url="http://identity",
            internal_token=settings.internal_service_token,
            timeout_seconds=5.0,
            transport=identity_transport,
        ),
    )


def _use(monkeypatch: pytest.MonkeyPatch, ledger_app: FastAPI, identity_app: FastAPI) -> None:
    _install(monkeypatch, ASGITransport(app=ledger_app), ASGITransport(app=identity_app))


async def _lookup(token: str | None, card_number: str) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(
            "/api/v1/transfers/recipient", params={"card_number": card_number}, headers=headers
        )


async def test_finds_the_recipient_and_shows_only_a_first_name_and_initial(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    seen: list[str] = []
    _use(monkeypatch, _ledger_app(seen=seen), _identity_app())
    spaced = f"{_CARD[:4]} {_CARD[4:8]} {_CARD[8:12]} {_CARD[12:]}"

    response = await _lookup(issue_access_token(uuid.uuid4()), spaced)

    assert response.status_code == 200
    assert response.json() == {
        "wallet_id": str(_WALLET),
        "currency": "UZS",
        "display_name": "Aziza K.",
        "own": False,
    }
    assert seen == [_CARD]  # spaces dropped before asking ledger-service


async def test_says_when_the_card_is_the_callers_own(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _use(monkeypatch, _ledger_app(), _identity_app())

    response = await _lookup(issue_access_token(_OWNER), _CARD)

    assert response.json()["own"] is True


async def test_a_mistyped_number_is_rejected_before_any_lookup(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    seen: list[str] = []
    _use(monkeypatch, _ledger_app(seen=seen), _identity_app())
    typo = _CARD[:-1] + str((int(_CARD[-1]) + 1) % 10)

    response = await _lookup(issue_access_token(uuid.uuid4()), typo)

    assert response.status_code == 422
    assert response.json()["title"] == "Invalid Card Number"
    assert seen == []


@pytest.mark.parametrize(
    ("ledger_kwargs", "identity_kwargs"),
    [
        ({"found": False}, {}),
        ({"status": "FROZEN"}, {}),
        ({}, {"status": "BLOCKED"}),
        ({}, {"code": 404}),
    ],
    ids=["no such card", "wallet frozen", "owner blocked", "owner missing"],
)
async def test_every_reason_a_card_cannot_receive_looks_the_same(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_kwargs: dict, identity_kwargs: dict
) -> None:
    _use(monkeypatch, _ledger_app(**ledger_kwargs), _identity_app(**identity_kwargs))

    response = await _lookup(issue_access_token(uuid.uuid4()), _CARD)

    assert response.status_code == 404
    assert response.json()["title"] == "Recipient Not Found"
    assert response.json()["detail"] == "no wallet can receive money at this card number"


async def test_a_service_that_cannot_answer_is_not_reported_as_no_recipient(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    token = issue_access_token(uuid.uuid4())

    _install(monkeypatch, httpx.MockTransport(refuse), ASGITransport(app=_identity_app()))
    assert (await _lookup(token, _CARD)).status_code == 503

    # A token identity-service rejects is a deployment fault, not "no such person".
    _use(monkeypatch, _ledger_app(), _identity_app(code=403))
    response = await _lookup(token, _CARD)
    assert response.status_code == 503
    assert response.json()["title"] == "Recipient Lookup Unavailable"


async def test_needs_a_signed_in_customer(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _ledger_app(), _identity_app())

    assert (await _lookup(None, _CARD)).status_code == 401


def test_display_name_never_gives_the_full_last_name() -> None:
    assert display_name("Aziza", "Karimova") == "Aziza K."
    assert display_name(" Ali ", " valiyev ") == "Ali V."
    assert display_name("Madonna", "") == "Madonna"
