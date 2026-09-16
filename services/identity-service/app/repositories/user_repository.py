from uuid import UUID

from sqlalchemy import select
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
