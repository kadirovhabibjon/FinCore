"""Asking for money end to end: the request, the notification to the
person asked (through Kafka), paying it as a transfer, and declining."""

import httpx

from e2e_client import FinCoreClient, User, idempotency_key, wait_until


def _requests(api: FinCoreClient, who: User) -> list[dict]:
    response = api.gateway.get("/api/v1/money-requests", headers=who.auth)
    assert response.status_code == 200
    return response.json()


def _notified(api: FinCoreClient, who: User, kind: str) -> dict | None:
    items = api.gateway.get("/api/v1/notifications", headers=who.auth).json()["items"]
    return next((item for item in items if item["type"] == kind), None)


def _ask(api: FinCoreClient, asker: User, wallet: str, card: str, amount: str) -> dict:
    response = api.gateway.post(
        "/api/v1/money-requests",
        json={"wallet_id": wallet, "from_card_number": card, "amount": amount, "note": "Dinner"},
        headers=asker.auth,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_request_is_paid_as_a_transfer_exactly_once(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    asker, payer = user, other_user
    asker_wallet = api.create_wallet(asker)
    payer_wallet = api.funded_wallet(payer, 100_000)
    payer_card = api.wallet(payer, payer_wallet)["card_number"]

    request = _ask(api, asker, asker_wallet, payer_card, "250.00")
    assert (request["status"], request["counterparty_name"]) == ("PENDING", "E2E U.")
    # Nothing has moved, and the person asked hears about it.
    assert api.wallet(payer, payer_wallet)["balance_minor"] == 100_000
    asked = wait_until(lambda: _notified(api, payer, "money_request.created"))
    assert asked["body"].startswith("E2E U. asks you for 250.00 UZS")
    [incoming] = _requests(api, payer)
    assert (incoming["direction"], incoming["id"]) == ("INCOMING", request["id"])

    def pay(key: dict[str, str]) -> httpx.Response:
        return api.gateway.post(
            f"/api/v1/money-requests/{request['id']}/pay",
            json={"source_wallet_id": payer_wallet},
            headers={**payer.auth, **key},
        )

    # Only the person asked can pay it.
    assert (
        api.gateway.post(
            f"/api/v1/money-requests/{request['id']}/pay",
            json={"source_wallet_id": asker_wallet},
            headers={**asker.auth, **idempotency_key()},
        ).status_code
        == 404
    )
    key = idempotency_key()
    paid = pay(key)
    assert paid.status_code == 200 and paid.json()["status"] == "PAID"
    assert pay(key).json() == paid.json()  # a retry is answered, not paid again
    assert pay(idempotency_key()).status_code == 409  # and a new attempt is refused

    assert api.wallet(payer, payer_wallet)["balance_minor"] == 75_000
    assert api.wallet(asker, asker_wallet)["balance_minor"] == 25_000
    assert _requests(api, asker)[0]["status"] == "PAID"
    # It arrived like any transfer: in history, and behind the bell.
    history = api.gateway.get("/api/v1/transactions", headers=asker.auth).json()
    assert [(t["direction"], t["amount_minor"]) for t in history] == [("IN", 25_000)]
    assert wait_until(lambda: _notified(api, asker, "transfer.received"))


def test_a_declined_request_moves_nothing_and_tells_the_asker(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    asker, payer = user, other_user
    asker_wallet = api.create_wallet(asker)
    payer_wallet = api.funded_wallet(payer, 10_000)
    payer_card = api.wallet(payer, payer_wallet)["card_number"]
    request = _ask(api, asker, asker_wallet, payer_card, "50.00")

    declined = api.gateway.post(
        f"/api/v1/money-requests/{request['id']}/decline", headers=payer.auth
    )

    assert declined.status_code == 200 and declined.json()["status"] == "DECLINED"
    assert api.wallet(payer, payer_wallet)["balance_minor"] == 10_000
    told = wait_until(lambda: _notified(api, asker, "money_request.declined"))
    assert told["body"] == "E2E U. declined your request for 50.00 UZS."
    assert (
        api.gateway.post(
            f"/api/v1/money-requests/{request['id']}/pay",
            json={"source_wallet_id": payer_wallet},
            headers={**payer.auth, **idempotency_key()},
        ).status_code
        == 409
    )
    assert api.gateway.get("/api/v1/money-requests").status_code == 401
