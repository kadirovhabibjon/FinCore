"""Operator commands, run inside the service's container:

    docker compose exec identity-service python -m app.cli grant-role <email> <ROLE>
    docker compose exec identity-service python -m app.cli revoke-role <email> <ROLE>

Registration only ever grants USER, and no HTTP endpoint grants roles —
so the first ADMIN (and every SUPPORT/ADMIN after it) is created by
someone with shell access to the running system, never over the network.
"""

import argparse
import asyncio
import sys

from fincore_common import EventType
from sqlalchemy import delete, select

from app.db import session as db_session
from app.domain.role import RoleName, UserRole
from app.repositories.user_repository import UserRepository
from app.services import two_factor
from app.services.outbox import user_outbox_event


async def _change_role(email: str, role: RoleName, *, grant: bool) -> str:
    async with db_session.async_session_factory() as session:
        user = await UserRepository(session).get_by_email(email.strip().lower())
        if user is None:
            raise SystemExit(f"no user with email {email!r}")

        existing = await session.execute(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role_name == role.value)
        )
        has_role = existing.scalar_one_or_none() is not None

        if grant and not has_role:
            session.add(UserRole(user_id=user.id, role_name=role.value))
        elif not grant and has_role:
            await session.execute(
                delete(UserRole).where(
                    UserRole.user_id == user.id, UserRole.role_name == role.value
                )
            )
        if grant != has_role:
            # Audited in the same transaction; actor_user_id is None
            # because an operator at a shell, not a signed-in user, did it.
            event = EventType.USER_ROLE_GRANTED if grant else EventType.USER_ROLE_REVOKED
            session.add(user_outbox_event(user, event, actor_user_id=None, role=role.value))
        await session.commit()
        roles = sorted(await UserRepository(session).get_role_names(user.id))
    await db_session.engine.dispose()
    return f"{email}: roles now {', '.join(roles) or '(none)'}"


async def _disable_two_factor(email: str) -> str:
    async with db_session.async_session_factory() as session:
        user = await UserRepository(session).get_by_email(email.strip().lower())
        if user is None:
            raise SystemExit(f"no user with email {email!r}")
        was_on = user.two_factor_enabled
        # Audited like every other change; no signed-in actor did it.
        await two_factor.disable_by_operator(session, user)
    await db_session.engine.dispose()
    return f"{email}: two-step sign-in {'turned off' if was_on else 'was already off'}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("grant-role", "revoke-role"):
        command = commands.add_parser(name)
        command.add_argument("email")
        command.add_argument("role", choices=[role.value for role in RoleName])
    # For someone locked out of their mailbox, after checking who they are.
    commands.add_parser("disable-two-factor").add_argument("email")
    args = parser.parse_args(argv)

    if args.command == "disable-two-factor":
        message = asyncio.run(_disable_two_factor(args.email))
    else:
        message = asyncio.run(
            _change_role(args.email, RoleName(args.role), grant=args.command == "grant-role")
        )
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
