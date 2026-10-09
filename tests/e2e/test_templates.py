"""Saved payments through the real gateway: saved, listed, removed, and
checked when saved the way the payment itself would be."""

from e2e_client import FinCoreClient, User


def test_a_service_and_a_transfer_are_saved_and_removed(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    destination = api.create_wallet(other_user)
    card = api.wallet(other_user, destination)["card_number"]

    assert api.gateway.get("/api/v1/templates").status_code == 401
    phone = api.gateway.post(
        "/api/v1/templates",
        json={"name": "My phone", "kind": "SERVICE", "service_code": "beeline",
              "account": "90 123 45 67", "amount": "50000"},
        headers=user.auth,
    )
    friend = api.gateway.post(
        "/api/v1/templates",
        json={"name": "Friend", "kind": "TRANSFER", "card_number": card},
        headers=user.auth,
    )
    nobody = api.gateway.post(
        "/api/v1/templates",
        json={"name": "Nobody", "kind": "TRANSFER", "card_number": "9955000000000006"},
        headers=user.auth,
    )

    assert phone.status_code == 201 and friend.status_code == 201
    assert (phone.json()["service_account"], phone.json()["amount_minor"]) == (
        "+998901234567",
        5_000_000,
    )
    assert (friend.json()["recipient_name"], friend.json()["currency"]) == ("E2E U.", "UZS")
    assert nobody.status_code in (404, 422)  # no such card, or not a valid number

    mine = api.gateway.get("/api/v1/templates", headers=user.auth).json()
    assert {item["name"] for item in mine} == {"My phone", "Friend"}
    assert api.gateway.get("/api/v1/templates", headers=other_user.auth).json() == []

    template_id = phone.json()["id"]
    assert (
        api.gateway.delete(f"/api/v1/templates/{template_id}", headers=other_user.auth).status_code
        == 404
    )
    assert (
        api.gateway.delete(f"/api/v1/templates/{template_id}", headers=user.auth).status_code == 204
    )
    left = api.gateway.get("/api/v1/templates", headers=user.auth).json()
    assert [item["name"] for item in left] == ["Friend"]
