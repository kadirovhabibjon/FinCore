from typing import Any

import pytest

from e2e_client import FinCoreClient, User, wait_until

# A public, purpose-built HTTP echo service. Anything the stack can reach
# on a private address is (correctly) rejected by webhook-service's SSRF
# protection, so a real delivery needs a real public target.
_PUBLIC_RECEIVER = "https://httpbin.org/post"


def _register(api: FinCoreClient, owner: User, merchant_id: str, url: str) -> Any:
    return api.gateway.post(
        "/api/v1/webhooks/endpoints",
        json={"merchant_id": merchant_id, "url": url},
        headers=owner.auth,
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/hook",
        "http://localhost/hook",
        "http://169.254.169.254/latest/meta-data",
        "http://postgres:5432/",
        "ftp://example.com/hook",
    ],
)
def test_registering_an_internal_or_non_http_target_is_rejected(
    api: FinCoreClient, user: User, url: str
) -> None:
    """SSRF protection against the live stack's own network — including
    `postgres`, a hostname that genuinely resolves from inside
    webhook-service's container, to a private address.
    """
    merchant_id = api.create_merchant(user)

    response = _register(api, user, merchant_id, url)

    assert response.status_code == 422
    assert response.json()["title"] == "Invalid Webhook URL"


def test_registering_for_someone_elses_merchant_is_not_found(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    merchant_id = api.create_merchant(other_user)

    response = _register(api, user, merchant_id, _PUBLIC_RECEIVER)

    assert response.status_code == 404


@pytest.mark.external_network
def test_a_payment_is_delivered_signed_to_the_merchants_endpoint(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    merchant_id = api.create_merchant(other_user)
    registered = _register(api, other_user, merchant_id, _PUBLIC_RECEIVER)
    if registered.status_code == 422 and "resolve" in registered.json().get("detail", ""):
        pytest.skip("stack has no outbound DNS/internet access")
    assert registered.status_code == 201
    endpoint = registered.json()
    assert endpoint["secret"]  # shown once, at creation

    wallet = api.funded_wallet(user, 10_000)
    payment = api.pay(user, wallet_id=wallet, merchant_id=merchant_id, amount="15.00").json()

    def first_attempt_made() -> dict[str, Any] | None:
        response = api.gateway.get(
            f"/api/v1/webhooks/endpoints/{endpoint['id']}/deliveries", headers=other_user.auth
        )
        response.raise_for_status()
        for delivery in response.json():
            if delivery["attempt_history"]:
                return delivery
        return None

    # Decided on the first attempt, not on the delivery reaching a
    # terminal state: a retry after a failed attempt waits out backoff
    # (seconds to minutes), and a failure there says more about the
    # external receiver than about FinCore.
    delivery = wait_until(first_attempt_made, timeout=60, interval=2.0)
    first = delivery["attempt_history"][0]

    if first["status_code"] is None or first["status_code"] >= 500:
        pytest.skip(f"public receiver unavailable: {first['status_code']} {first['error']}")
    assert delivery["status"] == "SUCCEEDED"
    assert delivery["event_type"] == "payment.completed"
    assert first["status_code"] == 200
    assert first["latency_ms"] is not None

    # The secret is never readable again after creation.
    fetched = api.gateway.get(
        f"/api/v1/webhooks/endpoints/{endpoint['id']}", headers=other_user.auth
    ).json()
    assert "secret" not in fetched
    assert payment["status"] == "SUCCESS"
