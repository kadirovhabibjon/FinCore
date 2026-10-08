"""Paying a service provider through the real stack: the catalogue, a
payment that moves the money like any other, and what the customer is
told about it."""

from e2e_client import FinCoreClient, User, idempotency_key, wait_until


def _pay(api: FinCoreClient, user: User, code: str, wallet: str, account: str, amount: str) -> dict:
    response = api.gateway.post(
        f"/api/v1/services/{code}/payments",
        json={"source_wallet_id": wallet, "account": account, "amount": amount},
        headers={**user.auth, **idempotency_key()},
    )
    return {"status_code": response.status_code, **response.json()}


def test_the_catalogue_is_for_signed_in_customers(api: FinCoreClient, user: User) -> None:
    assert api.gateway.get("/api/v1/services").status_code == 401
    listed = api.gateway.get("/api/v1/services", headers=user.auth)

    assert listed.status_code == 200
    by_code = {service["code"]: service for service in listed.json()}
    assert by_code["beeline"]["account_kind"] == "PHONE"
    assert by_code["electricity"]["category"] == "UTILITIES"


def test_a_mobile_top_up_moves_the_money_and_is_in_history_and_the_bell(
    api: FinCoreClient, user: User
) -> None:
    wallet = api.funded_wallet(user, 10_000_000)

    paid = _pay(api, user, "beeline", wallet, "90 123-45-67", "25000.00")

    assert paid["status_code"] == 201 and paid["status"] == "SUCCESS"
    assert (paid["service_code"], paid["service_account"]) == ("beeline", "+998901234567")
    after = api.wallet(user, wallet)
    assert (after["balance_minor"], after["held_minor"]) == (7_500_000, 0)

    history = api.gateway.get("/api/v1/transactions", headers=user.auth).json()
    assert any(item["id"] == paid["id"] and item["type"] == "PAYMENT" for item in history)

    def told() -> dict | None:
        items = api.gateway.get("/api/v1/notifications", headers=user.auth).json()["items"]
        return next((item for item in items if item["type"] == "payment.completed"), None)

    notification = wait_until(told)
    assert "25,000.00 UZS to Beeline" in notification["body"]
    assert notification["params"]["counterparty"] == "Beeline"


def test_what_cannot_be_paid_is_refused_and_moves_nothing(api: FinCoreClient, user: User) -> None:
    wallet = api.funded_wallet(user, 10_000_000)
    dollars = api.create_wallet(user, "USD")

    bad_account = _pay(api, user, "electricity", wallet, "12", "5000")
    too_little = _pay(api, user, "electricity", wallet, "1234567", "10")
    wrong_currency = _pay(api, user, "electricity", dollars, "1234567", "5000")
    no_such = _pay(api, user, "moon-cable", wallet, "1234567", "5000")
    too_poor = _pay(api, user, "electricity", wallet, "1234567", "500000")

    assert (bad_account["status_code"], bad_account["title"]) == (422, "Invalid Service Account")
    assert (too_little["status_code"], too_little["title"]) == (422, "Amount Out Of Range")
    assert (wrong_currency["status_code"], wrong_currency["title"]) == (422, "Currency Mismatch")
    assert (no_such["status_code"], no_such["title"]) == (404, "Service Not Found")
    # More than the wallet holds: a payment that failed, not a refusal.
    assert too_poor["status_code"] == 201 and too_poor["status"] == "FAILED"
    assert api.wallet(user, wallet)["balance_minor"] == 10_000_000
