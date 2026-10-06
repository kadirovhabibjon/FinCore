"""Currency exchange through the whole stack: a live rate, two ledger
postings, balances, history and the bell."""

import httpx
import pytest

from e2e_client import FinCoreClient, User, idempotency_key, wait_until


def _quote(api: FinCoreClient, user: User, source: str, destination: str, amount: str) -> dict:
    response = api.gateway.get(
        "/api/v1/exchanges/quote",
        params={"source_wallet_id": source, "destination_wallet_id": destination, "amount": amount},
        headers=user.auth,
    )
    if response.status_code == 503:
        # The rate provider can't be reached from here (an offline run):
        # nothing to test end to end, and exchange correctly refuses.
        pytest.skip("exchange rates are not reachable from this environment")
    assert response.status_code == 200, response.text
    return response.json()


def test_exchanging_moves_exactly_the_quoted_amounts_and_keeps_the_ledger_balanced(
    api: FinCoreClient, user: User
) -> None:
    uzs = api.funded_wallet(user, 5_000_000_00)
    usd = api.create_wallet(user, "USD")

    quote = _quote(api, user, uzs, usd, "1000000.00")
    assert quote["source_amount_minor"] == 1_000_000_00
    bought = quote["destination_amount_minor"]
    assert bought > 0

    def exchange(expected: int, key: dict[str, str]) -> httpx.Response:
        return api.gateway.post(
            "/api/v1/exchanges",
            json={
                "source_wallet_id": uzs,
                "destination_wallet_id": usd,
                "amount": "1000000.00",
                "expected_destination_amount_minor": expected,
            },
            headers={**user.auth, **key},
        )

    # A different amount than the one quoted exchanges nothing.
    assert exchange(bought + 1, idempotency_key()).status_code == 409
    assert api.wallet(user, uzs)["balance_minor"] == 5_000_000_00

    key = idempotency_key()
    done = exchange(bought, key)
    assert done.status_code == 201, done.text
    assert done.json()["status"] == "COMPLETED"
    assert exchange(bought, key).json() == done.json()  # a retry is not a second exchange

    assert api.wallet(user, uzs)["balance_minor"] == 4_000_000_00
    assert api.wallet(user, usd)["balance_minor"] == bought

    # And back again: a round trip never gives more than it started with.
    back = _quote(api, user, usd, uzs, f"{bought // 100}.{bought % 100:02d}")
    returned = api.gateway.post(
        "/api/v1/exchanges",
        json={
            "source_wallet_id": usd,
            "destination_wallet_id": uzs,
            "amount": f"{bought // 100}.{bought % 100:02d}",
            "expected_destination_amount_minor": back["destination_amount_minor"],
        },
        headers={**user.auth, **idempotency_key()},
    )
    assert returned.json()["status"] == "COMPLETED"
    assert api.wallet(user, usd)["balance_minor"] == 0
    assert api.wallet(user, uzs)["balance_minor"] <= 5_000_000_00

    history = api.gateway.get("/api/v1/transactions", headers=user.auth).json()
    assert [(t["type"], t["direction"], t["status"]) for t in history] == [
        ("EXCHANGE", "SELF", "COMPLETED"),
        ("EXCHANGE", "SELF", "COMPLETED"),
    ]

    def told() -> dict | None:
        items = api.gateway.get("/api/v1/notifications", headers=user.auth).json()["items"]
        return next((i for i in items if i["type"] == "exchange.completed"), None)

    assert "You exchanged" in wait_until(told)["body"]
    # Every posting the exchanges made balances, and no wallet went negative.
    report = api.reconciliation_report()
    assert report["is_clean"], report


def test_an_exchange_the_wallet_cannot_cover_takes_nothing(api: FinCoreClient, user: User) -> None:
    uzs = api.funded_wallet(user, 1_000_00)
    usd = api.create_wallet(user, "USD")
    quote = _quote(api, user, uzs, usd, "900000.00")

    response = api.gateway.post(
        "/api/v1/exchanges",
        json={
            "source_wallet_id": uzs,
            "destination_wallet_id": usd,
            "amount": "900000.00",
            "expected_destination_amount_minor": quote["destination_amount_minor"],
        },
        headers={**user.auth, **idempotency_key()},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "FAILED"
    assert response.json()["failure_reason"] == "Insufficient Funds"
    assert api.wallet(user, uzs)["balance_minor"] == 1_000_00
    assert api.wallet(user, usd)["balance_minor"] == 0


def test_exchange_is_only_between_ones_own_wallets(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    mine = api.funded_wallet(user, 10_000_00)
    theirs = api.create_wallet(other_user, "USD")

    quote = api.gateway.get(
        "/api/v1/exchanges/quote",
        params={"source_wallet_id": mine, "destination_wallet_id": theirs, "amount": "100.00"},
        headers=user.auth,
    )

    assert quote.status_code == 404
    assert api.gateway.get("/api/v1/exchanges/quote").status_code == 401
