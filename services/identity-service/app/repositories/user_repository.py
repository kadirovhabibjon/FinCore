from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.role import UserRole
from app.domain.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        result = await self._session.execute(select(User).where(User.phone == phone))
        return result.scalar_one_or_none()

    def add(self, user: User) -> None:
        self._session.add(user)

    async def get_role_names(self, user_id: UUID) -> list[str]:
        result = await self._session.execute(
            select(UserRole.role_name).where(UserRole.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_role_names_for(self, user_ids: list[UUID]) -> dict[UUID, list[str]]:
        """Batched form of `get_role_names`, for listing many users
        without one roles query each."""
        roles: dict[UUID, list[str]] = {user_id: [] for user_id in user_ids}
        if not user_ids:
            return roles
        result = await self._session.execute(
            select(UserRole.user_id, UserRole.role_name).where(UserRole.user_id.in_(user_ids))
        )
        for user_id, role_name in result.all():
            roles[user_id].append(role_name)
        return roles

    async def search(self, query: str | None, *, limit: int, offset: int) -> list[User]:
        """Admin lookup (ADR-0005): a full user id matches exactly;
        anything else is a case-insensitive substring of email or phone.
        Newest first."""
        statement = select(User)
        if query:
            text = query.strip()
            try:
                statement = statement.where(User.id == UUID(text))
            except ValueError:
                pattern = f"%{text.lower()}%"
                statement = statement.where(
                    or_(func.lower(User.email).like(pattern), User.phone.like(f"%{text}%"))
                )
        result = await self._session.execute(
            statement.order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())
