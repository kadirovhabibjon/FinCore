import uuid

from e2e_client import FinCoreClient, User


def test_a_registered_user_can_log_in_and_read_their_own_profile(
    api: FinCoreClient, user: User
) -> None:
    response = api.gateway.get("/api/v1/users/me", headers=user.auth)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user.id
    assert body["email"] == user.email
    assert "password" not in body and "password_hash" not in body


def test_a_token_issued_by_identity_is_accepted_by_other_services(
    api: FinCoreClient, user: User
) -> None:
    """ledger-service verifies identity-service's JWT locally via the
    published JWKS (ADR-0003) — no call back to identity per request.
    """
    wallet_id = api.create_wallet(user)

    assert api.wallet(user, wallet_id)["balance_minor"] == 0


def test_requests_without_a_token_get_a_problem_details_401(api: FinCoreClient) -> None:
    response = api.gateway.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 401


def test_wrong_password_is_rejected(api: FinCoreClient, user: User) -> None:
    response = api.gateway.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "not-the-password"}
    )

    assert response.status_code == 401


def test_refresh_rotates_the_token_and_reusing_the_old_one_revokes_the_session(
    api: FinCoreClient, user: User
) -> None:
    """spec Section 5: "reusing an old refresh token revokes the whole
    session family."
    """
    rotated = api.gateway.post(
        "/api/v1/auth/refresh", json={"refresh_token": user.refresh_token}
    )
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh_token"]
    assert new_refresh != user.refresh_token

    replayed = api.gateway.post("/api/v1/auth/refresh", json={"refresh_token": user.refresh_token})
    assert replayed.status_code == 401

    # The replay revoked the whole session, so even the legitimately
    # rotated token no longer works.
    after_revocation = api.gateway.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_refresh}
    )
    assert after_revocation.status_code == 401


def test_logout_invalidates_the_refresh_token(api: FinCoreClient, user: User) -> None:
    logout = api.gateway.post("/api/v1/auth/logout", json={"refresh_token": user.refresh_token})
    assert logout.status_code == 204

    refresh = api.gateway.post("/api/v1/auth/refresh", json={"refresh_token": user.refresh_token})
    assert refresh.status_code == 401


def test_password_reset_gives_nothing_away_about_accounts(api: FinCoreClient) -> None:
    """Without the code from the email there is no way in, and no way to
    learn whether an address has an account. (Whether this stack can
    send email at all depends on its SMTP settings: 202 when it can, 503
    when it can't - either way the same for everyone. Only addresses
    that can't exist are used, so no real email is ever sent.)"""
    nobody = {"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com"}
    stranger = {"phone": "+998 90 000 00 01"}

    first = api.gateway.post("/api/v1/auth/password-reset/request", json=nobody)
    second = api.gateway.post("/api/v1/auth/password-reset/request", json=stranger)

    assert first.status_code in (202, 503)
    assert second.status_code == first.status_code

    guess = api.gateway.post(
        "/api/v1/auth/password-reset/confirm",
        json={**nobody, "code": "123456", "new_password": "a-brand-new-password"},
    )
    assert guess.status_code == 422
    assert guess.json()["title"] == "Invalid Or Expired Code"
