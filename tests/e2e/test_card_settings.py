"""What a customer sets on their own card, across the real services:
ledger-service keeps the name, the main flag and the block; payment-
service keeps and enforces the daily limit."""

from e2e_client import FinCoreClient, User


def test_a_card_can_be_named_and_another_made_the_main_one(
    api: FinCoreClient, user: User
) -> None:
    first = api.create_wallet(user, "UZS")
    second = api.create_wallet(user, "USD")

    named = api.gateway.patch(
        f"/api/v1/wallets/{second}", json={"name": "Travel"}, headers=user.auth
    )
    chosen = api.gateway.post(f"/api/v1/wallets/{second}/primary", headers=user.auth)
    listed = api.gateway.get("/api/v1/wallets", headers=user.auth).json()

    assert named.status_code == 200 and named.json()["name"] == "Travel"
    assert chosen.status_code == 200
    assert [(w["id"], w["is_primary"], w["name"]) for w in listed] == [
        (second, True, "Travel"),
        (first, False, None),
    ]


def test_a_blocked_card_sends_nothing_but_still_receives(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    mine = api.funded_wallet(user, 100_000)
    theirs = api.funded_wallet(other_user, 100_000)

    blocked = api.gateway.post(f"/api/v1/wallets/{mine}/block", headers=user.auth)
    out = api.transfer(user, source=mine, destination=theirs, amount="100.00").json()
    incoming = api.transfer(other_user, source=theirs, destination=mine, amount="50.00").json()

    assert blocked.status_code == 200 and blocked.json()["blocked"] is True
    assert out["status"] == "FAILED" and out["failure_reason"] == "Wallet Blocked"
    assert incoming["status"] == "COMPLETED"
    assert api.wallet(user, mine)["balance_minor"] == 105_000

    unblocked = api.gateway.post(f"/api/v1/wallets/{mine}/unblock", headers=user.auth)
    again = api.transfer(user, source=mine, destination=theirs, amount="100.00").json()

    assert unblocked.json()["blocked"] is False
    assert again["status"] == "COMPLETED"
    assert api.wallet(user, mine)["balance_minor"] == 95_000


def test_someone_else_cannot_block_or_limit_a_card(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    mine = api.create_wallet(user)

    block = api.gateway.post(f"/api/v1/wallets/{mine}/block", headers=other_user.auth)
    limit = api.gateway.put(
        f"/api/v1/limits/{mine}", json={"daily_limit": "1.00"}, headers=other_user.auth
    )

    assert block.status_code == limit.status_code == 404
    assert api.wallet(user, mine)["blocked"] is False


def test_the_daily_limit_covers_transfers_and_payments_together(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    mine = api.funded_wallet(user, 1_000_000)
    theirs = api.create_wallet(other_user)
    merchant = api.create_merchant(other_user)

    set_ = api.gateway.put(
        f"/api/v1/limits/{mine}", json={"daily_limit": "1000.00"}, headers=user.auth
    )
    sent = api.transfer(user, source=mine, destination=theirs, amount="600.00").json()
    paid = api.pay(user, wallet_id=mine, merchant_id=merchant, amount="300.00").json()
    over = api.transfer(user, source=mine, destination=theirs, amount="100.01").json()
    status = api.gateway.get(f"/api/v1/limits/{mine}", headers=user.auth).json()

    assert set_.status_code == 200
    assert sent["status"] == "COMPLETED" and paid["status"] == "SUCCESS"
    assert over["status"] == "FAILED" and over["failure_reason"] == "Daily Limit Exceeded"
    assert (status["spent_minor"], status["remaining_minor"]) == (90_000, 10_000)
    assert api.wallet(user, mine)["balance_minor"] == 910_000

    api.gateway.put(f"/api/v1/limits/{mine}", json={"daily_limit": None}, headers=user.auth)
    free = api.transfer(user, source=mine, destination=theirs, amount="5000.00").json()
    assert free["status"] == "COMPLETED"
