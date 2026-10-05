import uuid

import httpx

from e2e_client import FinCoreClient, User


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
