"""Forgot password: a code emailed to the account's address is the only
way to set a new password without the old one."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core.config import settings
from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.domain.password_reset import PasswordReset
from app.main import app
from app.services import mailer

pytestmark = pytest.mark.usefixtures("migrated_database")

_OLD = "correct-horse-battery"
_NEW = "brand-new-password-1"


class Outbox:
    """Stands in for the mail server: what would have been emailed."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send_reset_code(self, *, to: str, first_name: str, code: str) -> None:
        self.sent.append({"to": to, "first_name": first_name, "code": code})

    @property
    def code(self) -> str:
        return self.sent[-1]["code"]


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> Outbox:
    outbox = Outbox()
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(mailer, "send_reset_code", outbox.send_reset_code)
    return outbox


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient) -> dict:
    user = {
        "email": f"{uuid.uuid4().hex[:10]}@example.com",
        "phone": f"+99890{uuid.uuid4().int % 10**7:07d}",
        "password": _OLD,
        "first_name": "Aziza",
        "last_name": "Karimova",
    }
    response = await client.post("/api/v1/auth/register", json=user)
    assert response.status_code == 201
    return {**user, "id": response.json()["id"]}


async def _login(client: AsyncClient, user: dict, password: str) -> int:
    response = await client.post(
        "/api/v1/auth/login", json={"phone": user["phone"], "password": password}
    )
    return response.status_code


async def _request(client: AsyncClient, **identifier: str) -> int:
    return (await client.post("/api/v1/auth/password-reset/request", json=identifier)).status_code


async def _confirm(client: AsyncClient, user: dict, code: str, password: str = _NEW) -> int:
    response = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"phone": user["phone"], "code": code, "new_password": password},
    )
    return response.status_code


async def test_the_emailed_code_sets_a_new_password_and_signs_every_device_out(
    mail: Outbox,
) -> None:
    async with _client() as client:
        user = await _register(client)
        signed_in = (
            await client.post(
                "/api/v1/auth/login", json={"email": user["email"], "password": _OLD}
            )
        ).json()

        # Asked for with the phone number typed loosely, as on the login page.
        assert await _request(client, phone=user["phone"].replace("+998", "+998 ")) == 202
        assert mail.sent == [{"to": user["email"], "first_name": "Aziza", "code": mail.code}]
        assert len(mail.code) == 6 and mail.code.isdigit()

        assert await _confirm(client, user, mail.code) == 204

        assert await _login(client, user, _NEW) == 200
        assert await _login(client, user, _OLD) == 401
        # Whoever was signed in with the old password is out.
        refreshed = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": signed_in["refresh_token"]}
        )
        assert refreshed.status_code == 401
        # A code works once.
        assert await _confirm(client, user, mail.code, "yet-another-password") == 422

    async with db_session.async_session_factory() as session:
        events = (
            (
                await session.execute(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == user["id"],
                        OutboxEvent.event_type == "user.password_changed",
                    )
                )
            )
            .scalars()
            .all()
        )
        stored = (
            (
                await session.execute(
                    select(PasswordReset).where(PasswordReset.user_id == uuid.UUID(user["id"]))
                )
            )
            .scalars()
            .all()
        )
    assert len(events) == 1 and events[0].payload["sessions_revoked"] == 1
    # Only a hash of the code is ever stored.
    assert all(mail.code not in reset.code_hash and len(reset.code_hash) == 64 for reset in stored)


async def test_an_unknown_or_blocked_account_gets_the_same_answer_and_no_email(
    mail: Outbox,
) -> None:
    async with _client() as client:
        user = await _register(client)
        async with db_session.async_session_factory() as session:
            from app.domain.user import User, UserStatus

            await session.execute(
                update(User)
                .where(User.id == uuid.UUID(user["id"]))
                .values(status=UserStatus.BLOCKED)
            )
            await session.commit()

        unknown = await client.post(
            "/api/v1/auth/password-reset/request", json={"email": "nobody@example.com"}
        )
        blocked = await client.post(
            "/api/v1/auth/password-reset/request", json={"phone": user["phone"]}
        )
        guess = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"email": "nobody@example.com", "code": "123456", "new_password": _NEW},
        )

    assert (unknown.status_code, unknown.content) == (202, b"null")
    assert (blocked.status_code, blocked.content) == (202, b"null")
    assert mail.sent == []
    assert guess.status_code == 422
    assert guess.json()["title"] == "Invalid Or Expired Code"


async def test_a_code_dies_after_too_many_wrong_guesses(mail: Outbox) -> None:
    async with _client() as client:
        user = await _register(client)
        await _request(client, phone=user["phone"])
        wrong = "000000" if mail.code != "000000" else "111111"

        for _ in range(settings.password_reset_max_attempts):
            assert await _confirm(client, user, wrong) == 422
        # Even the right code no longer works.
        assert await _confirm(client, user, mail.code) == 422
        assert await _login(client, user, _OLD) == 200

        # A fresh code does.
        await _request(client, phone=user["phone"])
        assert await _confirm(client, user, mail.code) == 204


async def test_only_the_newest_unexpired_code_works(mail: Outbox) -> None:
    async with _client() as client:
        user = await _register(client)
        await _request(client, phone=user["phone"])
        first = mail.code
        await _request(client, phone=user["phone"])
        second = mail.code

        if first != second:
            assert await _confirm(client, user, first) == 422

        async with db_session.async_session_factory() as session:
            await session.execute(
                update(PasswordReset)
                .where(PasswordReset.user_id == uuid.UUID(user["id"]))
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()
        assert await _confirm(client, user, second) == 422
        assert await _login(client, user, _OLD) == 200


async def test_an_account_can_only_be_sent_so_many_codes_an_hour(mail: Outbox) -> None:
    async with _client() as client:
        user = await _register(client)
        for _ in range(settings.password_reset_max_requests_per_hour + 2):
            assert await _request(client, email=user["email"]) == 202

    assert len(mail.sent) == settings.password_reset_max_requests_per_hour


async def test_requests_are_validated(mail: Outbox) -> None:
    async with _client() as client:
        user = await _register(client)
        await _request(client, phone=user["phone"])

        both = await client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": user["email"], "phone": user["phone"]},
        )
        neither = await client.post("/api/v1/auth/password-reset/request", json={})
        short = await _confirm(client, user, mail.code, "short")
        letters = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"phone": user["phone"], "code": "12ab56", "new_password": _NEW},
        )
        # Rejected requests are not guesses: the code still works.
        assert await _confirm(client, user, mail.code) == 204

    assert both.status_code == neither.status_code == 422
    assert short == 422 and letters.status_code == 422


async def test_without_a_mail_server_reset_says_so_for_everyone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "smtp_host", "")
    async with _client() as client:
        user = await _register(client)
        known = await client.post(
            "/api/v1/auth/password-reset/request", json={"phone": user["phone"]}
        )
        unknown = await client.post(
            "/api/v1/auth/password-reset/request", json={"email": "nobody@example.com"}
        )

    assert known.status_code == unknown.status_code == 503
    assert known.json()["title"] == unknown.json()["title"] == "Password Reset Unavailable"
