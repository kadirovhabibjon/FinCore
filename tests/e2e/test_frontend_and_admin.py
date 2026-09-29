"""Phase 7 through the real gateway: the SPA is served on the same origin
as the API (ADR-0005), browsers keep the refresh token in an httpOnly
cookie (ADR-0006), and staff resolve fraud reviews and block users
through the admin API.
"""

import httpx

from e2e_client import FinCoreClient, User, wait_until
from test_fraud_flow import _HIGH_FREQUENCY_THRESHOLD, _LARGE_AMOUNT

_COOKIE_MODE = {"X-Refresh-Token-Transport": "cookie"}


def test_the_gateway_serves_the_spa_for_client_side_routes(api: FinCoreClient) -> None:
    for path in ("/", "/wallets/abc", "/admin/reviews"):
        response = api.gateway.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert '<div id="root">' in response.text
        assert "default-src 'self'" in response.headers["content-security-policy"]

    # An unknown API path is a 404 problem, never the SPA's HTML.
    unknown = api.gateway.get("/api/v1/does-not-exist")
    assert unknown.status_code == 404
    assert unknown.json()["title"] == "Not Found"


def _refresh_cookie(response: httpx.Response) -> str:
    [header] = [
        h for h in response.headers.get_list("set-cookie") if h.startswith("fincore_refresh=")
    ]
    return header


def test_a_browser_session_lives_in_the_httponly_cookie(api: FinCoreClient, user: User) -> None:
    login = api.gateway.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": user.password},
        headers=_COOKIE_MODE,
    )
    assert login.status_code == 200
    assert login.json()["refresh_token"] is None
    set_cookie = _refresh_cookie(login)
    assert "HttpOnly" in set_cookie and "SameSite=strict" in set_cookie
    cookie = {"Cookie": set_cookie.split(";", 1)[0]}

    refreshed = api.gateway.post("/api/v1/auth/refresh", headers={**_COOKIE_MODE, **cookie})
    assert refreshed.status_code == 200
    cookie = {"Cookie": _refresh_cookie(refreshed).split(";", 1)[0]}

    # Without the opt-in header the cookie alone is not accepted (CSRF).
    assert api.gateway.post("/api/v1/auth/refresh", headers=cookie).status_code == 401

    logout = api.gateway.post("/api/v1/auth/logout", headers={**_COOKIE_MODE, **cookie})
    assert logout.status_code == 204
    assert "Max-Age=0" in _refresh_cookie(logout)
    after = api.gateway.post("/api/v1/auth/refresh", headers={**_COOKIE_MODE, **cookie})
    assert after.status_code == 401


def _transfer_in_review(api: FinCoreClient, user: User, destination: str) -> tuple[str, dict]:
    source = api.funded_wallet(user, 70_000_000)
    for _ in range(_HIGH_FREQUENCY_THRESHOLD):
        api.transfer(user, source=source, destination=destination, amount="1.00")
    response = api.transfer(user, source=source, destination=destination, amount=_LARGE_AMOUNT)
    transfer = response.json()
    assert transfer["status"] == "PENDING" and transfer["fraud_decision"] == "REVIEW"
    return source, transfer


def test_an_admin_approves_a_reviewed_transfer_and_the_money_moves(
    api: FinCoreClient, user: User, other_user: User
) -> None:
    admin = api.grant_role(api.register_and_login(), "ADMIN")
    destination = api.create_wallet(other_user)
    _, transfer = _transfer_in_review(api, user, destination)

    queue = api.gateway.get("/api/v1/admin/reviews", headers=admin.auth).json()
    assert transfer["id"] in [item["id"] for item in queue]
    # A plain user can't see the queue, let alone decide.
    assert api.gateway.get("/api/v1/admin/reviews", headers=user.auth).status_code == 403

    decided = api.gateway.post(
        f"/api/v1/admin/reviews/{transfer['id']}", json={"decision": "APPROVE"}, headers=admin.auth
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "COMPLETED"
    assert decided.json()["reviewed_by_user_id"] == admin.id

    received = api.wallet(other_user, destination)["balance_minor"]
    assert received == 60_000_000 + _HIGH_FREQUENCY_THRESHOLD * 100
    again = api.gateway.post(
        f"/api/v1/admin/reviews/{transfer['id']}", json={"decision": "REJECT"}, headers=admin.auth
    )
    assert again.status_code == 409
    assert api.reconciliation_report()["balance_mismatches"] == []

    # fraud-service's REVIEW decision is filed under the transfer itself,
    # next to the transfer's own completion event.
    def trail() -> set[str] | None:
        actions = {log["action"] for log in api.audit_logs_for(transfer["id"])}
        return actions if {"FRAUD_REVIEW_REQUIRED", "TRANSFER_COMPLETED"} <= actions else None

    wait_until(trail)


def test_support_can_look_but_blocking_needs_admin_and_ends_the_session(
    api: FinCoreClient, user: User
) -> None:
    support = api.grant_role(api.register_and_login(), "SUPPORT")
    admin = api.grant_role(api.register_and_login(), "ADMIN")

    found = api.gateway.get("/api/v1/admin/users", params={"q": user.email}, headers=support.auth)
    assert [u["id"] for u in found.json()] == [user.id]
    by_support = api.gateway.post(
        f"/api/v1/admin/users/{user.id}/status", json={"status": "BLOCKED"}, headers=support.auth
    )
    assert by_support.status_code == 403

    blocked = api.gateway.post(
        f"/api/v1/admin/users/{user.id}/status", json={"status": "BLOCKED"}, headers=admin.auth
    )
    assert blocked.json()["status"] == "BLOCKED"
    refresh = api.gateway.post("/api/v1/auth/refresh", json={"refresh_token": user.refresh_token})
    assert refresh.status_code == 401
    login = api.gateway.post(
        "/api/v1/auth/login", json={"email": user.email, "password": user.password}
    )
    assert login.status_code == 401
    assert api.gateway.get("/api/v1/users/me", headers=user.auth).status_code == 401

    # transactions oversight spans every user.
    listing = api.gateway.get(
        "/api/v1/admin/transactions", params={"user_id": user.id}, headers=support.auth
    )
    assert listing.status_code == 200


def test_account_events_reach_the_audit_trail(api: FinCoreClient, user: User) -> None:
    """identity-service's outbox -> Kafka `users` topic -> audit-service
    (spec Section 18: USER_BLOCKED and admin actions are auditable)."""
    admin = api.grant_role(api.register_and_login(), "ADMIN")
    api.gateway.post(
        f"/api/v1/admin/users/{user.id}/status", json={"status": "BLOCKED"}, headers=admin.auth
    ).raise_for_status()

    def user_actions() -> list[dict] | None:
        logs = api.audit_logs_for(user.id)
        actions = {log["action"] for log in logs}
        return logs if {"USER_REGISTERED", "USER_LOGIN", "USER_BLOCKED"} <= actions else None

    logs = wait_until(user_actions)
    blocked = next(log for log in logs if log["action"] == "USER_BLOCKED")
    assert blocked["actor_id"] == admin.id
    assert blocked["result"] == "BLOCKED"
    assert blocked["resource_type"] == "User"
    login = next(log for log in logs if log["action"] == "USER_LOGIN")
    assert login["actor_id"] == user.id
    assert login["details"]["ip_address"]  # spec Section 18: "from where"

    def role_grants() -> list[dict] | None:
        logs = api.audit_logs_for(admin.id)
        return [log for log in logs if log["action"] == "USER_ROLE_GRANTED"] or None

    assert wait_until(role_grants)[0]["actor_id"] is None  # granted by the operator CLI
