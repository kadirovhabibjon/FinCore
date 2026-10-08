"""A customer writes to an operator and staff answer, through the real
gateway: the conversation, the staff inbox, and the bell."""

from e2e_client import FinCoreClient, User, wait_until


def test_a_customer_and_an_operator_talk(api: FinCoreClient, user: User, other_user: User) -> None:
    staff = api.grant_role(api.register_and_login(), "SUPPORT")
    thread = f"/api/v1/admin/support/threads/{user.id}"

    assert api.gateway.get("/api/v1/support/messages").status_code == 401
    assert api.gateway.get("/api/v1/admin/support/threads", headers=user.auth).status_code == 403

    written = api.gateway.post(
        "/api/v1/support/messages", json={"body": "My payment did not arrive."}, headers=user.auth
    )
    assert written.status_code == 201

    inbox = api.gateway.get("/api/v1/admin/support/threads", headers=staff.auth).json()
    mine = next(item for item in inbox["items"] if item["user_id"] == user.id)
    assert (mine["last_body"], mine["unread_count"], mine["status"]) == (
        "My payment did not arrive.",
        1,
        "OPEN",
    )
    assert inbox["waiting_count"] >= 1

    answered = api.gateway.post(
        f"{thread}/messages", json={"body": "We are checking it now."}, headers=staff.auth
    )
    assert answered.status_code == 201

    conversation = api.gateway.get("/api/v1/support/messages", headers=user.auth).json()
    assert [(m["sender"], m["body"]) for m in conversation["items"]] == [
        ("CUSTOMER", "My payment did not arrive."),
        ("STAFF", "We are checking it now."),
    ]
    assert conversation["unread_count"] == 1

    def told() -> dict | None:
        items = api.gateway.get("/api/v1/notifications", headers=user.auth).json()["items"]
        return next((item for item in items if item["type"] == "support.reply"), None)

    assert wait_until(told)["body"] == "We are checking it now."

    assert api.gateway.post("/api/v1/support/read", headers=user.auth).status_code == 204
    assert (
        api.gateway.get("/api/v1/support/messages", headers=user.auth).json()["unread_count"] == 0
    )
    # Someone else's conversation is their own.
    theirs = api.gateway.get("/api/v1/support/messages", headers=other_user.auth).json()
    assert theirs["items"] == []

    # This stack may be someone's running demo: don't leave it waiting in the inbox.
    resolved = api.gateway.post(f"{thread}/resolve", headers=staff.auth)
    assert resolved.status_code == 200 and resolved.json()["status"] == "RESOLVED"
