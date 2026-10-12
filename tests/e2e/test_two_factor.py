"""Two-step sign-in against the real stack. The suite's accounts live at
example.com, where no mail can arrive - which is exactly the case the
feature must refuse: it can't be turned on where a code could not be
read, so nobody is ever locked behind a dead mailbox."""

import uuid

from e2e_client import FinCoreClient, User


def test_it_cannot_be_turned_on_for_a_mailbox_no_code_can_reach(
    api: FinCoreClient, user: User
) -> None:
    before = api.gateway.get("/api/v1/users/me", headers=user.auth).json()
    wrong_password = api.gateway.post(
        "/api/v1/users/me/two-factor/enable",
        json={"current_password": "not-the-password"},
        headers=user.auth,
    )
    refused = api.gateway.post(
        "/api/v1/users/me/two-factor/enable",
        json={"current_password": user.password},
        headers=user.auth,
    )
    after = api.gateway.get("/api/v1/users/me", headers=user.auth).json()

    assert before["two_factor_enabled"] is False
    assert wrong_password.status_code == 422
    assert wrong_password.json()["title"] == "Incorrect Password"
    assert refused.status_code == 503
    assert refused.json()["title"] == "Two-Step Sign-In Unavailable"
    assert after["two_factor_enabled"] is False
    # And so the password alone still signs in.
    assert api.login(user.email, user.password)["access_token"]


def test_the_second_step_refuses_what_it_was_never_asked_for(api: FinCoreClient) -> None:
    unknown = api.gateway.post(
        "/api/v1/auth/login/verify",
        json={"challenge_id": str(uuid.uuid4()), "code": "123456"},
    )
    malformed = api.gateway.post(
        "/api/v1/auth/login/verify",
        json={"challenge_id": str(uuid.uuid4()), "code": "12345"},
    )
    anonymous = api.gateway.post(
        "/api/v1/users/me/two-factor/disable", json={"current_password": "x"}
    )

    assert unknown.status_code == 401
    assert unknown.json()["title"] == "Invalid Or Expired Code"
    assert malformed.status_code == 422
    assert anonymous.status_code == 401
