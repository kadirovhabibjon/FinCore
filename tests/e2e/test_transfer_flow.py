import uuid

import httpx

from e2e_client import FinCoreClient, User, wait_until


def test_a_transfer_moves_money_between_two_users_wallets(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    source = api.funded_wallet(user, 100_000)
    destination = api.create_wallet(other_user)

    response = api.transfer(user, source=source, destination=destination, amount="250.00")

    assert response.status_code == 201
    transfer = response.json()
    assert transfer["status"] == "COMPLETED"
    assert transfer["amount_minor"] == 25_000
    assert api.wallet(user, source)["balance_minor"] == 75_000
    assert api.wallet(other_user, destination)["balance_minor"] == 25_000


def test_the_transfer_appears_in_the_senders_transaction_history(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    source = api.funded_wallet(user, 10_000)
    destination = api.create_wallet(other_user)
    transfer = api.transfer(user, source=source, destination=destination, amount="10.00").json()

    history = api.gateway.get("/api/v1/transactions", headers=user.auth)
    single = api.gateway.get(f"/api/v1/transactions/{transfer['id']}", headers=user.auth)

    assert history.status_code == 200
    assert any(
        item["id"] == transfer["id"] and item["type"] == "TRANSFER"
        for item in history.json()
    )
    assert single.status_code == 200
    assert single.json()["reference"] == transfer["reference"]


def test_insufficient_funds_fails_the_transfer_and_moves_nothing(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    source = api.funded_wallet(user, 1_000)
    destination = api.create_wallet(other_user)

    response = api.transfer(user, source=source, destination=destination, amount="50.00")

    assert response.status_code == 201
    assert response.json()["status"] == "FAILED"
    assert api.wallet(user, source)["balance_minor"] == 1_000
    assert api.wallet(other_user, destination)["balance_minor"] == 0


def test_replaying_the_same_idempotency_key_moves_money_exactly_once(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    """spec Section 9.1: same key + same body returns the original
    response verbatim; the saga never runs a second time.
    """
    source = api.funded_wallet(user, 10_000)
    destination = api.create_wallet(other_user)
    key = {"Idempotency-Key": str(uuid.uuid4())}

    first = api.transfer(user, source=source, destination=destination, amount="30.00", headers=key)
    second = api.transfer(user, source=source, destination=destination, amount="30.00", headers=key)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert api.wallet(user, source)["balance_minor"] == 7_000


def test_reusing_an_idempotency_key_with_a_different_body_is_rejected(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    source = api.funded_wallet(user, 10_000)
    destination = api.create_wallet(other_user)
    key = {"Idempotency-Key": str(uuid.uuid4())}

    api.transfer(user, source=source, destination=destination, amount="10.00", headers=key)
    conflict = api.transfer(
        user, source=source, destination=destination, amount="20.00", headers=key
    )

    assert conflict.status_code == 422
    assert api.wallet(user, source)["balance_minor"] == 9_000


def test_transferring_from_someone_elses_wallet_is_not_found(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    victims_wallet = api.funded_wallet(other_user, 10_000)
    attackers_wallet = api.create_wallet(user)

    response = api.transfer(
        user, source=victims_wallet, destination=attackers_wallet, amount="10.00"
    )

    assert response.status_code == 404
    assert api.wallet(other_user, victims_wallet)["balance_minor"] == 10_000


def test_money_is_sent_to_a_card_number_after_seeing_who_it_belongs_to(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    """The Send page's flow end to end, across three services: the
    recipient shares their wallet's card number; the sender looks it up
    (payment-service asks ledger-service whose wallet it is and
    identity-service for the name) and sends to the wallet it names."""
    source = api.funded_wallet(user, 50_000)
    destination = api.create_wallet(other_user)
    card_number = api.wallet(other_user, destination)["card_number"]
    profile = api.gateway.get("/api/v1/users/me", headers=other_user.auth).json()

    spaced = " ".join(card_number[i : i + 4] for i in range(0, 16, 4))
    lookup = api.gateway.get(
        "/api/v1/transfers/recipient", params={"card_number": spaced}, headers=user.auth
    )

    assert lookup.status_code == 200
    recipient = lookup.json()
    assert recipient == {
        "wallet_id": destination,
        "currency": "UZS",
        # First name and last initial only: never the full name, email or phone.
        "display_name": f"{profile['first_name']} {profile['last_name'][0].upper()}.",
        "own": False,
    }

    response = api.transfer(
        user, source=source, destination=recipient["wallet_id"], amount="120.00"
    )

    assert response.json()["status"] == "COMPLETED"
    assert api.wallet(other_user, destination)["balance_minor"] == 12_000


def test_recipient_lookup_gives_nothing_away(api: FinCoreClient, user: User) -> None:
    own_wallet = api.create_wallet(user)
    own_card = api.wallet(user, own_wallet)["card_number"]
    typo = own_card[:-1] + str((int(own_card[-1]) + 1) % 10)

    def lookup(card_number: str, headers: dict[str, str] | None = None) -> httpx.Response:
        return api.gateway.get(
            "/api/v1/transfers/recipient", params={"card_number": card_number}, headers=headers
        )

    assert lookup(own_card).status_code == 401  # signed-in customers only
    assert lookup(own_card, headers=user.auth).json()["own"] is True
    assert lookup(typo, headers=user.auth).status_code == 422
    # Well-formed but nobody's: the same 404 a frozen wallet would get.
    assert lookup("9955000000000006", headers=user.auth).status_code == 404
    # The services' internal lookups are not reachable from outside.
    assert api.gateway.get(f"/internal/v1/users/{uuid.uuid4()}").status_code == 404
    assert (
        api.gateway.get(
            "/internal/v1/accounts/wallet-by-card", params={"card_number": own_card}
        ).status_code
        == 404
    )


def _notifications(api: FinCoreClient, who: User) -> dict:
    response = api.gateway.get("/api/v1/notifications", headers=who.auth)
    assert response.status_code == 200
    return response.json()


def test_both_people_see_a_transfer_in_history_and_are_notified(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    """Money sent from one customer to another shows up for both: in
    each one's history (with the direction and the other's name) and
    behind each one's bell. The notifications travel payment-service's
    outbox -> Kafka -> notification-service, so they are waited for."""
    source = api.funded_wallet(user, 50_000)
    destination = api.create_wallet(other_user)

    transfer = api.transfer(user, source=source, destination=destination, amount="75.00").json()
    assert transfer["status"] == "COMPLETED"

    def history(who: User) -> list[dict]:
        return api.gateway.get("/api/v1/transactions", headers=who.auth).json()

    [sent] = history(user)
    [received] = history(other_user)
    assert (sent["id"], sent["direction"], sent["counterparty_name"]) == (
        transfer["id"],
        "OUT",
        "E2E U.",
    )
    assert (received["id"], received["direction"], received["counterparty_name"]) == (
        transfer["id"],
        "IN",
        "E2E U.",
    )
    assert received["amount_minor"] == 7_500
    # The recipient can open it; the sender's own transfer resource stays the sender's.
    assert (
        api.gateway.get(f"/api/v1/transactions/{transfer['id']}", headers=other_user.auth)
    ).status_code == 200
    assert (
        api.gateway.get(f"/api/v1/transfers/{transfer['id']}", headers=other_user.auth)
    ).status_code == 404

    def both_notified() -> tuple[dict, dict] | None:
        mine, theirs = _notifications(api, user), _notifications(api, other_user)
        return (mine, theirs) if mine["items"] and theirs["items"] else None

    mine, theirs = wait_until(both_notified)

    assert theirs["unread_count"] == 1
    assert theirs["items"][0]["type"] == "transfer.received"
    assert theirs["items"][0]["body"] == "E2E U. sent you 75.00 UZS."
    assert mine["items"][0]["type"] == "transfer.completed"
    assert "75.00 UZS to E2E U." in mine["items"][0]["body"]

    # Opening the bell clears the recipient's badge and nobody else's.
    assert (
        api.gateway.post("/api/v1/notifications/read", headers=other_user.auth).status_code == 204
    )
    assert _notifications(api, other_user)["unread_count"] == 0
    assert _notifications(api, user)["unread_count"] == 1


def test_notifications_need_a_signed_in_customer(api: FinCoreClient) -> None:
    assert api.gateway.get("/api/v1/notifications").status_code == 401
    assert api.gateway.post("/api/v1/notifications/read").status_code == 401
