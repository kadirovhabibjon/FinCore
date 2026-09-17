from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal.schemas import CreatePostingRequest, PostingResponse
from app.core.auth import require_internal_service
from app.core.exceptions import PostingNotFoundError
from app.db.session import get_db
from app.domain.posting import PostingType
from app.repositories.posting_repository import PostingRepository
from app.services.postings import EntryInput, create_posting

router = APIRouter(
    prefix="/internal/v1/postings",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


@router.post("", response_model=PostingResponse, status_code=status.HTTP_201_CREATED)
async def post_posting(
    payload: CreatePostingRequest,
    session: AsyncSession = Depends(get_db),
) -> PostingResponse:
    posting = await create_posting(
        session,
        source_service=payload.source_service,
        source_id=payload.source_id,
        type=payload.type,
        currency=payload.currency,
        entries=[
            EntryInput(entry.account_id, entry.direction, entry.amount_minor)
            for entry in payload.entries
        ],
    )
    return PostingResponse.model_validate(posting)


@router.get("/{source_id}", response_model=PostingResponse)
async def get_posting(
    source_id: str,
    source_service: str = Query(...),
    type: PostingType = Query(...),
    session: AsyncSession = Depends(get_db),
) -> PostingResponse:
    """Lets a caller (payment-service's recovery worker) resolve the
    outcome of a posting call whose original response was lost to a
    timeout, per the transfer saga's "unknown outcome" branch (spec
    Section 10.1, ADR-0003).
    """
    posting = await PostingRepository(session).get_by_source(source_service, source_id, type)
    if posting is None:
        raise PostingNotFoundError(source_id)
    return PostingResponse.model_validate(posting)
