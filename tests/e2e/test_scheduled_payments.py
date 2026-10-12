"""Scheduled payments through the real gateway: what can be scheduled,
by whom, and that scheduling alone moves nothing. (That a due run is
made once, as an ordinary operation, is payment-service's own test:
only it can move a schedule's clock.)"""

from datetime import UTC, datetime

from e2e_client import FinCoreClient, User


def test_a_payment_is_scheduled_paused_and_removed(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    mine = api.funded_wallet(user, 10_000_000)
    theirs = api.create_wallet(other_user)
    card = api.wallet(other_user, theirs)["card_number"]
    url = "/api/v1/scheduled-payments"

    assert api.gateway.get(url).status_code == 401
    internet = api.gateway.post(
        url,
        json={"name": "Home internet", "kind": "SERVICE", "service_code": "uzonline",
              "account": "aziza_01", "source_wallet_id": mine, "amount": "150000",
              "interval": "MONTHLY", "day": 5},
        headers=user.auth,
    )
    rent = api.gateway.post(
        url,
        json={"name": "Rent", "kind": "TRANSFER", "card_number": card,
              "source_wallet_id": mine, "amount": "2500.00", "interval": "WEEKLY", "day": 1},
        headers=user.auth,
    )
    bad_day = api.gateway.post(
        url,
        json={"name": "x", "kind": "SERVICE", "service_code": "uzonline", "account": "aziza_01",
              "source_wallet_id": mine, "amount": "150000", "interval": "MONTHLY", "day": 31},
        headers=user.auth,
    )
    not_my_wallet = api.gateway.post(
        url,
        json={"name": "x", "kind": "SERVICE", "service_code": "uzonline", "account": "aziza_01",
              "source_wallet_id": theirs, "amount": "150000", "interval": "MONTHLY", "day": 5},
        headers=user.auth,
    )

    assert internet.status_code == 201 and rent.status_code == 201
    assert datetime.fromisoformat(internet.json()["next_run_at"]) > datetime.now(UTC)
    assert (rent.json()["recipient_name"], rent.json()["amount_minor"]) == ("E2E U.", 250_000)
    assert (bad_day.status_code, bad_day.json()["title"]) == (422, "Invalid Schedule")
    assert (not_my_wallet.status_code, not_my_wallet.json()["title"]) == (404, "Wallet Not Found")
    # Scheduling pays nothing.
    assert api.wallet(user, mine)["balance_minor"] == 10_000_000

    listed = api.gateway.get(url, headers=user.auth).json()
    assert {item["name"] for item in listed} == {"Home internet", "Rent"}
    assert api.gateway.get(url, headers=other_user.auth).json() == []

    one = f"{url}/{internet.json()['id']}"
    stranger = api.gateway.patch(one, json={"status": "PAUSED"}, headers=other_user.auth)
    assert stranger.status_code == 404
    paused = api.gateway.patch(one, json={"status": "PAUSED"}, headers=user.auth)
    assert paused.status_code == 200 and paused.json()["status"] == "PAUSED"
    assert api.gateway.delete(one, headers=other_user.auth).status_code == 404
    assert api.gateway.delete(one, headers=user.auth).status_code == 204
    # Leave nothing that would later move money on someone's demo stack.
    assert api.gateway.delete(f"{url}/{rent.json()['id']}", headers=user.auth).status_code == 204
    assert api.gateway.get(url, headers=user.auth).json() == []
