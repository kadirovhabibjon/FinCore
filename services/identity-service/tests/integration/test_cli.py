import pytest
from httpx import ASGITransport, AsyncClient

from app import cli
from app.domain.role import RoleName
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_USER = {
    "email": "turing@example.com",
    "phone": "+998901234000",
    "password": "enigma-bombe-1940",
    "first_name": "Alan",
    "last_name": "Turing",
}


async def _roles() -> list[str]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        tokens = (
            await client.post(
                "/api/v1/auth/login",
                json={"email": _USER["email"], "password": _USER["password"]},
            )
        ).json()
        me = await client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
    return me.json()["roles"]


async def test_grant_and_revoke_role_are_idempotent() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=_USER)

    granted = await cli._change_role("Turing@Example.com ", RoleName.ADMIN, grant=True)
    again = await cli._change_role(_USER["email"], RoleName.ADMIN, grant=True)
    assert await _roles() == ["ADMIN", "USER"]

    revoked = await cli._change_role(_USER["email"], RoleName.ADMIN, grant=False)
    assert await _roles() == ["USER"]

    assert granted.endswith("roles now ADMIN, USER")
    assert again.endswith("roles now ADMIN, USER")
    assert revoked.endswith("roles now USER")


async def test_unknown_email_exits_with_a_message() -> None:
    with pytest.raises(SystemExit, match="no user with email"):
        await cli._change_role("nobody@example.com", RoleName.ADMIN, grant=True)
