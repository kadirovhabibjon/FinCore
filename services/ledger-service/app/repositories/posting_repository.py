from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.posting import Posting, PostingType


class PostingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_source(
        self, source_service: str, source_id: str, type: PostingType
    ) -> Posting | None:
        result = await self._session.execute(
            select(Posting).where(
                Posting.source_service == source_service,
                Posting.source_id == source_id,
                Posting.type == type,
            )
        )
        return result.scalar_one_or_none()
