"""Two-step sign-in: after the password, a code emailed to the account."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app import cli
from app.core.config import settings
from app.db import session as db_session
from app.domain.login_code import LoginCode
from app.domain.outbox import OutboxEvent
from app.domain.role import RoleName, UserRole
from app.domain.user import User, UserStatus
from app.main import app
from app.services import mailer
from app.services.two_factor import email_hint

pytestmark = pytest.mark.usefixtures("migrated_database")

_PASSWORD = "correct-horse-battery"


class Outbox:
    """Stands in for the mail server: what would have been emailed."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_login_code(
        self, *, to: str, first_name: str, code: str, enabling: bool = False
    ) -> None:
        self.sent.append({"to": to, "code": code, "enabling": enabling})

    async def send_new_device(self, **_: object) -> None:
        return None

    @property
    def code(self) -> str:
        return self.sent[-1]["code"]


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> Outbox:
    outbox = Outbox()
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(mailer, "send_login_code", outbox.send_login_code)
    monkeypatch.setattr(mailer, "send_new_device", outbox.send_new_device)
    # Test accounts live at example.com, where real mail never goes;
    # here nothing is really sent, so they may have codes.
    monkeypatch.setattr(mailer, "is_deliverable", lambda address: True)
    return outbox


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient) -> dict:
    user = {
        "email": f"{uuid.uuid4().hex[:10]}@example.com",
        "phone": f"+99890{uuid.uuid4().int % 10**7:07d}",
        "password": _PASSWORD,
        "first_name": "Aziza",
        "last_name": "Karimova",
    }
    response = await client.post("/api/v1/auth/register", json=user)
    assert response.status_code == 201
    return {**user, "id": response.json()["id"]}


async def _signed_in(client: AsyncClient, user: dict) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": _PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _turn_on(client: AsyncClient, user: dict, mail: Outbox) -> None:
    headers = await _signed_in(client, user)
    begun = await client.post(
        "/api/v1/users/me/two-factor/enable",
        json={"current_password": _PASSWORD},
        headers=headers,
    )
    assert begun.status_code == 202, begun.text
    confirmed = await client.post(
        "/api/v1/users/me/two-factor/confirm",
        json={"challenge_id": begun.json()["challenge_id"], "code": mail.code},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text


def _other(code: str) -> str:
    return "000000" if code != "000000" else "111111"


async def test_turning_it_on_takes_the_password_and_a_code_from_the_mailbox(mail: Outbox) -> None:
    async with _client() as client:
        user = await _register(client)
        headers = await _signed_in(client, user)
        before = await client.get("/api/v1/users/me", headers=headers)
        wrong_password = await client.post(
            "/api/v1/users/me/two-factor/enable",
            json={"current_password": "not-it"},
            headers=headers,
        )
        begun = await client.post(
            "/api/v1/users/me/two-factor/enable",
            json={"current_password": _PASSWORD},
            headers=headers,
        )
        still_off = await client.get("/api/v1/users/me", headers=headers)
        challenge = begun.json()["challenge_id"]
        wrong_code = await client.post(
            "/api/v1/users/me/two-factor/confirm",
            json={"challenge_id": challenge, "code": _other(mail.code)},
            headers=headers,
        )
        confirmed = await client.post(
            "/api/v1/users/me/two-factor/confirm",
            json={"challenge_id": challenge, "code": mail.code},
            headers=headers,
        )
        again = await client.post(
            "/api/v1/users/me/two-factor/confirm",
            json={"challenge_id": challenge, "code": mail.code},
            headers=headers,
        )

    assert before.json()["two_factor_enabled"] is False
    assert wrong_password.status_code == 422
    assert wrong_password.json()["title"] == "Incorrect Password"
    assert begun.status_code == 202
    assert begun.json() | {"challenge_id": ""} == {
        "two_factor_required": True,
        "challenge_id": "",
        "email_hint": email_hint(user["email"]),
        "expires_in": 600,
    }
    assert mail.sent == [{"to": user["email"], "code": mail.code, "enabling": True}]
    # Asking is not enabling: a mailbox that never shows the code locks nobody out.
    assert still_off.json()["two_factor_enabled"] is False
    assert wrong_code.status_code == 401
    assert confirmed.status_code == 200 and confirmed.json()["two_factor_enabled"] is True
    assert again.status_code == 401  # a code works once

    async with db_session.async_session_factory() as session:
        events = (
            await session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == user["id"],
                    OutboxEvent.event_type == "user.profile_updated",
                )
            )
        ).scalars().all()
    assert [event.payload["changed_fields"] for event in events] == ["two_factor"]


async def test_the_password_alone_no_longer_signs_in(mail: Outbox) -> None:
    async with _client() as client:
        user = await _register(client)
        await _turn_on(client, user, mail)

        first = await client.post(
            "/api/v1/auth/login", json={"phone": user["phone"], "password": _PASSWORD}
        )
        challenge = first.json()["challenge_id"]
        wrong = await client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": challenge, "code": _other(mail.code)},
        )
        unknown = await client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": str(uuid.uuid4()), "code": mail.code},
        )
        right = await client.post(
            "/api/v1/auth/login/verify", json={"challenge_id": challenge, "code": mail.code}
        )
        replayed = await client.post(
            "/api/v1/auth/login/verify", json={"challenge_id": challenge, "code": mail.code}
        )
        me = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {right.json()['access_token']}"},
        )
        wrong_password = await client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": "nope"}
        )

    assert first.status_code == 202
    assert "access_token" not in first.json() and "set-cookie" not in first.headers
    assert first.json()["email_hint"] == email_hint(user["email"])
    assert mail.sent[-1] == {"to": user["email"], "code": mail.code, "enabling": False}
    assert wrong.status_code == unknown.status_code == replayed.status_code == 401
    assert wrong.json()["title"] == unknown.json()["title"] == "Invalid Or Expired Code"
    assert right.status_code == 200 and right.json()["refresh_token"]
    assert me.status_code == 200 and me.json()["two_factor_enabled"] is True
    # A wrong password is still just a wrong password: no code is sent.
    assert wrong_password.status_code == 401
    assert wrong_password.json()["title"] == "Invalid Credentials"
    assert len([m for m in mail.sent if not m["enabling"]]) == 1


async def test_the_second_step_sets_the_cookie_the_first_step_was_asked_for(mail: Outbox) -> None:
    cookie = {"X-Refresh-Token-Transport": "cookie"}
    async with _client() as client:
        user = await _register(client)
        await _turn_on(client, user, mail)
        first = await client.post(
            "/api/v1/auth/login",
            json={"email": user["email"], "password": _PASSWORD},
            headers=cookie,
        )
        second = await client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": first.json()["challenge_id"], "code": mail.code},
            headers=cookie,
        )

    assert first.status_code == 202 and "set-cookie" not in first.headers
    assert second.status_code == 200
    assert second.json()["refresh_token"] is None
    assert settings.refresh_cookie_name in second.headers["set-cookie"]
    assert "HttpOnly" in second.headers["set-cookie"]


async def test_a_code_dies_after_five_wrong_tries_and_with_time(mail: Outbox) -> None:
    async with _client() as client:
        user = await _register(client)
        await _turn_on(client, user, mail)

        async def challenge() -> str:
            response = await client.post(
                "/api/v1/auth/login", json={"email": user["email"], "password": _PASSWORD}
            )
            return response.json()["challenge_id"]

        async def verify(challenge_id: str, code: str) -> int:
            response = await client.post(
                "/api/v1/auth/login/verify", json={"challenge_id": challenge_id, "code": code}
            )
            return response.status_code

        guessed = await challenge()
        right = mail.code
        tries = [await verify(guessed, _other(right)) for _ in range(5)]
        after_five = await verify(guessed, right)

        expired = await challenge()
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(LoginCode)
                .where(LoginCode.id == uuid.UUID(expired))
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()
        too_late = await verify(expired, mail.code)

        # A newer code replaces the older one.
        older = await challenge()
        older_code = mail.code
        newer = await challenge()
        replaced = await verify(older, older_code)
        works = await verify(newer, mail.code)

    assert tries == [401] * 5
    assert after_five == 401  # even the right code, now
    assert too_late == 401
    assert replaced == 401 and works == 200


async def test_guesses_made_at_once_do_not_each_get_a_free_try(mail: Outbox) -> None:
    async with _client() as client:
        user = await _register(client)
        await _turn_on(client, user, mail)
        first = await client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )
        challenge = first.json()["challenge_id"]
        wrong = _other(mail.code)
        await asyncio.gather(
            *(
                client.post(
                    "/api/v1/auth/login/verify", json={"challenge_id": challenge, "code": wrong}
                )
                for _ in range(12)
            )
        )
        after = await client.post(
            "/api/v1/auth/login/verify", json={"challenge_id": challenge, "code": mail.code}
        )

    async with db_session.async_session_factory() as session:
        record = await session.get(LoginCode, uuid.UUID(challenge))
    assert record is not None and record.attempts == 5  # counted, then refused
    assert after.status_code == 401


async def test_only_so_many_codes_are_emailed_in_an_hour(
    mail: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _client() as client:
        user = await _register(client)
        await _turn_on(client, user, mail)  # that was one
        monkeypatch.setattr(settings, "login_code_max_requests_per_hour", 3)
        statuses = [
            (
                await client.post(
                    "/api/v1/auth/login", json={"email": user["email"], "password": _PASSWORD}
                )
            ).status_code
            for _ in range(3)
        ]
        refused = await client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )

    assert statuses == [202, 202, 429]
    assert refused.json()["title"] == "Too Many Codes"
    assert len(mail.sent) == 3


async def test_it_cannot_be_turned_on_where_no_code_could_arrive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _client() as client:
        user = await _register(client)
        headers = await _signed_in(client, user)

        async def enable() -> tuple[int, str]:
            response = await client.post(
                "/api/v1/users/me/two-factor/enable",
                json={"current_password": _PASSWORD},
                headers=headers,
            )
            return response.status_code, response.json()["title"]

        no_mail_server = await enable()
        monkeypatch.setattr(settings, "smtp_host", "smtp.test")
        # The account's address is at example.com: nobody receives mail there.
        undeliverable = await enable()
        me = await client.get("/api/v1/users/me", headers=headers)

    assert no_mail_server == undeliverable == (503, "Two-Step Sign-In Unavailable")
    assert me.json()["two_factor_enabled"] is False


async def test_turning_it_off_takes_the_password(mail: Outbox) -> None:
    async with _client() as client:
        user = await _register(client)
        await _turn_on(client, user, mail)
        first = await client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )
        tokens = await client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": first.json()["challenge_id"], "code": mail.code},
        )
        headers = {"Authorization": f"Bearer {tokens.json()['access_token']}"}
        refused = await client.post(
            "/api/v1/users/me/two-factor/disable",
            json={"current_password": "not-it"},
            headers=headers,
        )
        off = await client.post(
            "/api/v1/users/me/two-factor/disable",
            json={"current_password": _PASSWORD},
            headers=headers,
        )
        plain = await client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )
        anonymous = await client.post(
            "/api/v1/users/me/two-factor/disable", json={"current_password": _PASSWORD}
        )

    assert refused.status_code == 422 and refused.json()["title"] == "Incorrect Password"
    assert off.status_code == 200 and off.json()["two_factor_enabled"] is False
    assert plain.status_code == 200 and plain.json()["access_token"]
    assert anonymous.status_code == 401


async def test_someone_elses_challenge_confirms_nothing(mail: Outbox) -> None:
    async with _client() as client:
        victim, attacker = await _register(client), await _register(client)
        attacker_headers = await _signed_in(client, attacker)
        victim_headers = await _signed_in(client, victim)
        begun = await client.post(
            "/api/v1/users/me/two-factor/enable",
            json={"current_password": _PASSWORD},
            headers=attacker_headers,
        )
        # The attacker's own challenge and code, presented as the victim...
        crossed = await client.post(
            "/api/v1/users/me/two-factor/confirm",
            json={"challenge_id": begun.json()["challenge_id"], "code": mail.code},
            headers=victim_headers,
        )
        # ...and a code meant for turning it on, presented to sign in.
        as_login = await client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": begun.json()["challenge_id"], "code": mail.code},
        )
        victim_me = await client.get("/api/v1/users/me", headers=victim_headers)

    assert crossed.status_code == 401 and as_login.status_code == 401
    assert victim_me.json()["two_factor_enabled"] is False


async def test_an_account_blocked_between_the_two_steps_does_not_get_in(mail: Outbox) -> None:
    async with _client() as client:
        user = await _register(client)
        await _turn_on(client, user, mail)
        first = await client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(User)
                .where(User.id == uuid.UUID(user["id"]))
                .values(status=UserStatus.BLOCKED)
            )
            await session.commit()
        second = await client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": first.json()["challenge_id"], "code": mail.code},
        )

    assert second.status_code == 401


async def test_the_admin_console_door_is_checked_before_a_code_is_sent(mail: Outbox) -> None:
    console = {"X-Refresh-Token-Transport": "cookie-admin"}
    async with _client() as client:
        customer, staff = await _register(client), await _register(client)
        async with db_session.async_session_factory() as session:
            session.add(UserRole(user_id=uuid.UUID(staff["id"]), role_name=RoleName.ADMIN.value))
            await session.commit()
        await _turn_on(client, customer, mail)
        await _turn_on(client, staff, mail)
        sent_before = len(mail.sent)

        refused = await client.post(
            "/api/v1/auth/login",
            json={"email": customer["email"], "password": _PASSWORD},
            headers=console,
        )
        first = await client.post(
            "/api/v1/auth/login",
            json={"email": staff["email"], "password": _PASSWORD},
            headers=console,
        )
        second = await client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": first.json()["challenge_id"], "code": mail.code},
            headers=console,
        )

    assert refused.status_code == 403 and refused.json()["title"] == "Insufficient Role"
    assert len(mail.sent) == sent_before + 1  # only the staff account's
    assert second.status_code == 200
    assert f"{settings.refresh_cookie_name}_admin" in second.headers["set-cookie"]


async def test_an_operator_can_turn_it_off_for_someone_locked_out(mail: Outbox) -> None:
    async with _client() as client:
        user = await _register(client)
        await _turn_on(client, user, mail)

    assert "turned off" in await cli._disable_two_factor(user["email"])
    assert "already off" in await cli._disable_two_factor(user["email"])

    async with db_session.async_session_factory() as session:
        stored = await session.get(User, uuid.UUID(user["id"]))
        events = (
            await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.aggregate_id == user["id"])
                .order_by(OutboxEvent.created_at)
            )
        ).scalars().all()
    assert stored is not None and stored.two_factor_enabled is False
    # Turned on by the customer, off by nobody who was signed in.
    changes = [e.payload for e in events if e.payload.get("changed_fields") == "two_factor"]
    assert [change["actor_user_id"] for change in changes] == [user["id"], None]


@pytest.mark.parametrize("code", ["12345", "1234567", "12345a", ""])
async def test_a_code_is_six_digits(code: str) -> None:
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/login/verify", json={"challenge_id": str(uuid.uuid4()), "code": code}
        )

    assert response.status_code == 422
