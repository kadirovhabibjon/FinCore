"""The bell beyond transfers: payments, refunds and staff announcements,
through the gateway and (for payments) the outbox -> Kafka ->
notification-service pipeline."""

from e2e_client import FinCoreClient, User, wait_until


def _bell(api: FinCoreClient, who: User) -> dict:
    response = api.gateway.get("/api/v1/notifications", headers=who.auth)
    assert response.status_code == 200
    return response.json()


def _of_type(api: FinCoreClient, who: User, kind: str) -> dict | None:
    return next((item for item in _bell(api, who)["items"] if item["type"] == kind), None)


def test_a_payment_and_its_refund_notify_the_payer_and_the_merchant(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    merchant_id = api.create_merchant(other_user, name="Choyxona")
    wallet = api.funded_wallet(user, 50_000)

    payment = api.pay(user, wallet_id=wallet, merchant_id=merchant_id, amount="120.00").json()
    assert payment["status"] == "SUCCESS"

    paid = wait_until(lambda: _of_type(api, user, "payment.completed"))
    received = wait_until(lambda: _of_type(api, other_user, "payment.received"))
    assert paid["body"] == f"You paid 120.00 UZS to Choyxona — reference {payment['reference']}"
    assert paid["params"] == {
        "amount": "120.00 UZS",
        "reference": payment["reference"],
        "counterparty": "Choyxona",
    }
    assert "Choyxona received a payment of 120.00 UZS" in received["body"]
    # The merchant is not told about its own customers' other notifications.
    assert _of_type(api, other_user, "payment.completed") is None

    assert api.refund(other_user, payment_id=payment["id"], amount="120.00").status_code == 201

    refunded = wait_until(lambda: _of_type(api, user, "payment.refunded"))
    assert refunded["title"] == "Refund received"
    assert "was refunded by Choyxona" in refunded["body"]
    assert refunded["params"]["partial"] is False


def test_an_announcement_reaches_every_customer_until_it_is_withdrawn(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    admin = api.grant_role(api.register_and_login(), "ADMIN")
    message = {"title": "E2E announcement", "body": "Published by the end-to-end suite."}

    assert api.gateway.post("/api/v1/admin/announcements", json=message).status_code == 401
    refused = api.gateway.post("/api/v1/admin/announcements", json=message, headers=user.auth)
    assert refused.status_code == 403

    published = api.gateway.post("/api/v1/admin/announcements", json=message, headers=admin.auth)
    assert published.status_code == 201
    announcement_id = published.json()["id"]
    try:
        for customer in (user, other_user):
            item = next(i for i in _bell(api, customer)["items"] if i["id"] == announcement_id)
            assert (item["type"], item["title"], item["read"]) == (
                "announcement",
                "E2E announcement",
                False,
            )
        unread_before = _bell(api, user)["unread_count"]
        assert unread_before >= 1
        assert api.gateway.post("/api/v1/notifications/read", headers=user.auth).status_code == 204
        assert _bell(api, user)["unread_count"] == 0
        assert _bell(api, other_user)["unread_count"] >= 1
    finally:
        # This stack may be someone's running demo: leave nothing in real bells.
        withdrawn = api.gateway.delete(
            f"/api/v1/admin/announcements/{announcement_id}", headers=admin.auth
        )
    assert withdrawn.status_code == 204
    assert all(i["id"] != announcement_id for i in _bell(api, user)["items"])
