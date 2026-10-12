"""Savings goals through the real ledger: money set aside really leaves
the wallet, comes back whole, and the goal's figure follows the ledger."""

from e2e_client import FinCoreClient, User, idempotency_key


def _move(api: FinCoreClient, user: User, goal: str, how: str, wallet: str, amount: str) -> dict:
    response = api.gateway.post(
        f"/api/v1/savings-goals/{goal}/{how}",
        json={"wallet_id": wallet, "amount": amount},
        headers={**user.auth, **idempotency_key()},
    )
    return {"status_code": response.status_code, **response.json()}


def test_money_is_set_aside_and_taken_back(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    wallet = api.funded_wallet(user, 100_000)
    url = "/api/v1/savings-goals"

    assert api.gateway.get(url).status_code == 401
    created = api.gateway.post(
        url, json={"name": "New phone", "currency": "UZS", "target": "5000"}, headers=user.auth
    )
    assert created.status_code == 201
    goal = created.json()["id"]

    put_in = _move(api, user, goal, "deposit", wallet, "300.00")
    assert put_in["status"] == "COMPLETED"
    assert api.wallet(user, wallet)["balance_minor"] == 70_000
    # Set aside is out of reach: the wallet can no longer send it.
    too_much = api.transfer(
        user, source=wallet, destination=api.create_wallet(other_user), amount="800.00"
    ).json()
    assert too_much["status"] == "FAILED"

    beyond_wallet = _move(api, user, goal, "deposit", wallet, "9000.00")
    assert (beyond_wallet["status"], beyond_wallet["failure_reason"]) == (
        "FAILED",
        "Insufficient Funds",
    )
    beyond_goal = _move(api, user, goal, "withdraw", wallet, "300.01")
    assert (beyond_goal["status"], beyond_goal["failure_reason"]) == (
        "FAILED",
        "Insufficient Savings",
    )
    saved = api.gateway.get(url, headers=user.auth).json()[0]["saved_minor"]
    assert saved == 30_000 and api.wallet(user, wallet)["balance_minor"] == 70_000

    # Someone else can neither see nor touch it.
    assert api.gateway.get(url, headers=other_user.auth).json() == []
    stranger = api.gateway.delete(f"{url}/{goal}", headers=other_user.auth)
    assert stranger.status_code == 404
    not_empty = api.gateway.delete(f"{url}/{goal}", headers=user.auth)
    assert not_empty.status_code == 409 and not_empty.json()["title"] == "Goal Not Empty"

    taken = _move(api, user, goal, "withdraw", wallet, "300.00")
    assert taken["status"] == "COMPLETED"
    assert api.wallet(user, wallet)["balance_minor"] == 100_000
    movements = api.gateway.get(f"{url}/{goal}/movements", headers=user.auth).json()
    assert [(m["direction"], m["status"]) for m in movements] == [
        ("WITHDRAW", "COMPLETED"),
        ("WITHDRAW", "FAILED"),
        ("DEPOSIT", "FAILED"),
        ("DEPOSIT", "COMPLETED"),
    ]
    assert api.gateway.delete(f"{url}/{goal}", headers=user.auth).status_code == 204
    assert api.gateway.get(url, headers=user.auth).json() == []
    # The ledger still balances, and nothing went negative.
    report = api.reconciliation_report()
    assert report["is_clean"], report
