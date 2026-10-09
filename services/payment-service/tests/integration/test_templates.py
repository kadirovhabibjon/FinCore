"""Saved payments (templates): a service and account, or a recipient's
card, kept so the form comes filled in."""

import uuid

import pytest
from fincore_common import generate_card_number
from httpx import ASGITransport, AsyncClient

from app.api.v1 import templates as templates_api
from app.main import app
from tests.integration import test_recipient_lookup as lookup

pytestmark = pytest.mark.usefixtures("migrated_database")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wire_recipient(monkeypatch: pytest.MonkeyPatch, **ledger_options: object) -> None:
    lookup._use(monkeypatch, lookup._ledger_app(**ledger_options), lookup._identity_app())


async def test_a_service_payment_is_saved_with_its_account_in_one_form(issue_access_token) -> None:
    token = issue_access_token(uuid.uuid4())

    async with _client() as client:
        saved = await client.post(
            "/api/v1/templates",
            json={
                "name": "  My   phone ",
                "kind": "SERVICE",
                "service_code": "beeline",
                "account": "90 123-45-67",
                "amount": "50000",
            },
            headers=_auth(token),
        )
        no_amount = await client.post(
            "/api/v1/templates",
            json={"name": "Gas", "kind": "SERVICE", "service_code": "natural-gas",
                  "account": "0012 3456"},
            headers=_auth(token),
        )
        listed = await client.get("/api/v1/templates", headers=_auth(token))

    assert saved.status_code == 201
    body = saved.json()
    assert body | {"id": "", "created_at": ""} == {
        "id": "",
        "kind": "SERVICE",
        "name": "My phone",
        "service_code": "beeline",
        "service_account": "+998901234567",
        "card_number": None,
        "recipient_name": None,
        "currency": "UZS",
        "amount_minor": 5_000_000,
        "created_at": "",
    }
    assert no_amount.json()["amount_minor"] is None
    assert no_amount.json()["service_account"] == "00123456"
    assert {item["name"] for item in listed.json()} == {"My phone", "Gas"}


async def test_a_transfer_is_saved_with_who_the_card_belongs_to(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_recipient(monkeypatch)
    token = issue_access_token(uuid.uuid4())
    card = lookup._CARD
    spaced = f"{card[:4]} {card[4:8]} {card[8:12]} {card[12:]}"

    async with _client() as client:
        saved = await client.post(
            "/api/v1/templates",
            json={"name": "Aziza", "kind": "TRANSFER", "card_number": spaced, "amount": "100.50"},
            headers=_auth(token),
        )

    assert saved.status_code == 201
    body = saved.json()
    assert (body["card_number"], body["recipient_name"]) == (card, "Aziza K.")
    assert (body["currency"], body["amount_minor"]) == ("UZS", 10_050)
    assert body["service_code"] is None and body["service_account"] is None


async def test_what_could_not_be_paid_is_not_saved(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_recipient(monkeypatch, found=False)
    token = issue_access_token(uuid.uuid4())
    cases = [
        ({"kind": "SERVICE", "service_code": "moon-cable", "account": "1234567"}, 404,
         "Service Not Found"),
        ({"kind": "SERVICE", "service_code": "beeline", "account": "12"}, 422,
         "Invalid Service Account"),
        ({"kind": "SERVICE", "service_code": "beeline", "account": "901234567", "amount": "5"},
         422, "Amount Out Of Range"),
        ({"kind": "SERVICE", "service_code": "beeline", "account": "901234567", "amount": "x"},
         422, "Invalid Amount"),
        ({"kind": "SERVICE", "service_code": "beeline"}, 422, "Invalid Template"),
        ({"kind": "SERVICE", "service_code": "beeline", "account": "901234567",
          "card_number": lookup._CARD}, 422, "Invalid Template"),
        ({"kind": "TRANSFER"}, 422, "Invalid Template"),
        ({"kind": "TRANSFER", "card_number": lookup._CARD, "service_code": "beeline"}, 422,
         "Invalid Template"),
        ({"kind": "TRANSFER", "card_number": "1234567890123456"}, 422, "Invalid Card Number"),
        ({"kind": "TRANSFER", "card_number": generate_card_number()}, 404, "Recipient Not Found"),
        ({"kind": "TRANSFER", "card_number": lookup._CARD, "amount": "0"}, 404,
         "Recipient Not Found"),
    ]

    async with _client() as client:
        for payload, status_code, title in cases:
            response = await client.post(
                "/api/v1/templates", json={"name": "x", **payload}, headers=_auth(token)
            )
            assert (response.status_code, response.json()["title"]) == (status_code, title), payload
        blank = await client.post(
            "/api/v1/templates",
            json={"name": "   ", "kind": "SERVICE", "service_code": "beeline",
                  "account": "901234567"},
            headers=_auth(token),
        )
        listed = await client.get("/api/v1/templates", headers=_auth(token))

    assert blank.status_code == 422
    assert listed.json() == []


async def test_templates_are_the_owners_alone(issue_access_token) -> None:
    mine, theirs = issue_access_token(uuid.uuid4()), issue_access_token(uuid.uuid4())
    payload = {"name": "Phone", "kind": "SERVICE", "service_code": "ucell", "account": "935554433"}

    async with _client() as client:
        saved = (await client.post("/api/v1/templates", json=payload, headers=_auth(mine))).json()
        seen_by_other = await client.get("/api/v1/templates", headers=_auth(theirs))
        deleted_by_other = await client.delete(
            f"/api/v1/templates/{saved['id']}", headers=_auth(theirs)
        )
        anonymous = await client.get("/api/v1/templates")
        still_there = await client.get("/api/v1/templates", headers=_auth(mine))
        deleted = await client.delete(f"/api/v1/templates/{saved['id']}", headers=_auth(mine))
        again = await client.delete(f"/api/v1/templates/{saved['id']}", headers=_auth(mine))
        gone = await client.get("/api/v1/templates", headers=_auth(mine))

    assert seen_by_other.json() == []
    assert deleted_by_other.status_code == 404
    assert deleted_by_other.json()["title"] == "Template Not Found"
    assert anonymous.status_code == 401
    assert [item["id"] for item in still_there.json()] == [saved["id"]]
    assert deleted.status_code == 204 and again.status_code == 404
    assert gone.json() == []


async def test_there_is_a_limit_to_how_many_can_be_saved(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    monkeypatch.setattr(templates_api, "MAX_TEMPLATES", 3)
    token = issue_access_token(uuid.uuid4())
    payload = {"kind": "SERVICE", "service_code": "comnet", "account": "user1"}

    async with _client() as client:
        for number in range(3):
            response = await client.post(
                "/api/v1/templates", json={"name": f"t{number}", **payload}, headers=_auth(token)
            )
            assert response.status_code == 201
        one_more = await client.post(
            "/api/v1/templates", json={"name": "t3", **payload}, headers=_auth(token)
        )
        # Someone else's count is their own.
        other = await client.post(
            "/api/v1/templates",
            json={"name": "t", **payload},
            headers=_auth(issue_access_token(uuid.uuid4())),
        )

    assert one_more.status_code == 409 and one_more.json()["title"] == "Too Many Templates"
    assert other.status_code == 201
