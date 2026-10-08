import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import session as db_session
from app.domain.role import RoleName, UserRole
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_PASSWORD = "correct-horse-battery"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient, name: str, *roles: RoleName) -> dict:
    user = {
        "email": f"{name}@example.com",
        "phone": f"+99890{uuid.uuid4().int % 10**7:07d}",
        "password": _PASSWORD,
        "first_name": name.capitalize(),
        "last_name": "Test",
    }
    registered = (await client.post("/api/v1/auth/register", json=user)).json()
    if roles:
        async with db_session.async_session_factory() as session:
            for role in roles:
                session.add(UserRole(user_id=uuid.UUID(registered["id"]), role_name=role.value))
            await session.commit()
    tokens = (
        await client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )
    ).json()
    return {**registered, **tokens, "email": user["email"]}


def _auth(account: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {account['access_token']}"}


async def test_me_reports_the_callers_roles() -> None:
    async with _client() as client:
        admin = await _register(client, "ada", RoleName.ADMIN)
        response = await client.get("/api/v1/users/me", headers=_auth(admin))

    assert response.status_code == 200
    assert response.json()["roles"] == ["ADMIN", "USER"]


async def test_a_plain_user_cannot_reach_the_admin_api() -> None:
    async with _client() as client:
        user = await _register(client, "plain")
        search = await client.get("/api/v1/admin/users", headers=_auth(user))
        block = await client.post(
            f"/api/v1/admin/users/{user['id']}/status",
            json={"status": "BLOCKED"},
            headers=_auth(user),
        )

    assert search.status_code == 403
    assert search.json()["title"] == "Insufficient Role"
    assert block.status_code == 403


async def test_support_can_look_users_up_but_not_change_status() -> None:
    async with _client() as client:
        support = await _register(client, "helper", RoleName.SUPPORT)
        target = await _register(client, "customer")

        by_email = await client.get(
            "/api/v1/admin/users", params={"q": "CUSTOMER@"}, headers=_auth(support)
        )
        by_id = await client.get(
            "/api/v1/admin/users", params={"q": target["id"]}, headers=_auth(support)
        )
        detail = await client.get(f"/api/v1/admin/users/{target['id']}", headers=_auth(support))
        block = await client.post(
            f"/api/v1/admin/users/{target['id']}/status",
            json={"status": "BLOCKED"},
            headers=_auth(support),
        )

    assert [u["email"] for u in by_email.json()] == ["customer@example.com"]
    assert [u["id"] for u in by_id.json()] == [target["id"]]
    assert detail.json()["roles"] == ["USER"]
    assert block.status_code == 403


async def test_blocking_a_user_ends_every_way_they_could_stay_signed_in() -> None:
    async with _client() as client:
        admin = await _register(client, "boss", RoleName.ADMIN)
        target = await _register(client, "mallory")

        blocked = await client.post(
            f"/api/v1/admin/users/{target['id']}/status",
            json={"status": "BLOCKED"},
            headers=_auth(admin),
        )
        refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": target["refresh_token"]}
        )
        login = await client.post(
            "/api/v1/auth/login", json={"email": target["email"], "password": _PASSWORD}
        )
        me = await client.get("/api/v1/users/me", headers=_auth(target))

        reactivated = await client.post(
            f"/api/v1/admin/users/{target['id']}/status",
            json={"status": "ACTIVE"},
            headers=_auth(admin),
        )
        login_again = await client.post(
            "/api/v1/auth/login", json={"email": target["email"], "password": _PASSWORD}
        )

    assert blocked.status_code == 200
    assert blocked.json()["status"] == "BLOCKED"
    assert refresh.status_code == 401
    assert login.status_code == 401
    assert me.status_code == 401
    assert reactivated.json()["status"] == "ACTIVE"
    assert login_again.status_code == 200


async def test_an_admin_cannot_change_their_own_status() -> None:
    async with _client() as client:
        admin = await _register(client, "root", RoleName.ADMIN)
        response = await client.post(
            f"/api/v1/admin/users/{admin['id']}/status",
            json={"status": "SUSPENDED"},
            headers=_auth(admin),
        )

    assert response.status_code == 409


async def test_unknown_users_are_not_found() -> None:
    async with _client() as client:
        admin = await _register(client, "chief", RoleName.ADMIN)
        detail = await client.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=_auth(admin))
        status_change = await client.post(
            f"/api/v1/admin/users/{uuid.uuid4()}/status",
            json={"status": "BLOCKED"},
            headers=_auth(admin),
        )

    assert detail.status_code == 404
    assert status_change.status_code == 404


async def test_staff_see_how_many_accounts_there_are_and_when_they_were_created() -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.domain.user import User, UserStatus

    today = datetime.now(UTC).date()
    async with _client() as client:
        support = await _register(client, f"sup{uuid.uuid4().hex[:8]}", RoleName.SUPPORT)
        before = (
            await client.get("/api/v1/admin/users/stats", headers=_auth(support))
        ).json()

        earlier = await _register(client, f"old{uuid.uuid4().hex[:8]}")
        blocked = await _register(client, f"blk{uuid.uuid4().hex[:8]}")
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(User)
                .where(User.id == uuid.UUID(earlier["id"]))
                .values(created_at=datetime.now(UTC) - timedelta(days=2))
            )
            await session.execute(
                update(User)
                .where(User.id == uuid.UUID(blocked["id"]))
                .values(status=UserStatus.BLOCKED)
            )
            await session.commit()

        stats = await client.get(
            "/api/v1/admin/users/stats", params={"days": 3}, headers=_auth(support)
        )
        as_customer = await client.get("/api/v1/admin/users/stats", headers=_auth(earlier))
        anonymous = await client.get("/api/v1/admin/users/stats")
        too_many = await client.get(
            "/api/v1/admin/users/stats", params={"days": 91}, headers=_auth(support)
        )

    assert as_customer.status_code == 403 and anonymous.status_code == 401
    assert too_many.status_code == 422
    assert stats.status_code == 200
    body = stats.json()
    # Other tests share this database: compare with what was there before.
    assert body["total"] == before["total"] + 2
    assert body["by_status"].get("BLOCKED", 0) == before["by_status"].get("BLOCKED", 0) + 1
    assert sum(body["by_status"].values()) == body["total"]
    assert [day["date"] for day in body["days"]] == [
        str(today - timedelta(days=2)),
        str(today - timedelta(days=1)),
        str(today),
    ]
    assert body["days"][0]["registered"] >= 1
    assert body["days"][2]["registered"] == before["days"][-1]["registered"] + 1
