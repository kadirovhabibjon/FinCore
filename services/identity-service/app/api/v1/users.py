from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_current_user
from app.api.v1.schemas import UserResponse
from app.domain.user import User

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
