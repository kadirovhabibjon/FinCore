from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.merchant import Merchant


class MerchantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, merchant_id: UUID) -> Merchant | None:
        return await self._session.get(Merchant, merchant_id)

    async def list_for_owner(self, owner_user_id: UUID) -> list[Merchant]:
        result = await self._session.execute(
            select(Merchant)
            .where(Merchant.owner_user_id == owner_user_id)
            .order_by(Merchant.created_at.desc())
        )
        return list(result.scalars().all())
