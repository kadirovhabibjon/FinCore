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
