from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal.schemas import DeadLetterResponse
from app.core import kafka as kafka_module
from app.core.auth import require_internal_service
from app.core.config import settings
from app.core.exceptions import DeadLetterNotFoundError
from app.db.session import get_db
from app.repositories.dead_letter_repository import DeadLetterRepository
from app.services.replay import replay_dead_letter

router = APIRouter(
    prefix="/internal/v1/dead-letters",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


@router.get("", response_model=list[DeadLetterResponse])
async def list_dead_letters(session: AsyncSession = Depends(get_db)) -> list[DeadLetterResponse]:
    rows = await DeadLetterRepository(session).list_unreplayed()
    return [DeadLetterResponse.model_validate(row) for row in rows]


@router.post("/{dead_letter_id}/replay", status_code=status.HTTP_204_NO_CONTENT)
async def replay(dead_letter_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    dead_letter = await DeadLetterRepository(session).get(dead_letter_id)
    if dead_letter is None:
        raise DeadLetterNotFoundError(str(dead_letter_id))
    await replay_dead_letter(
        session, dead_letter, kafka_module.side_channel_producer, settings.transfers_topic
    )
