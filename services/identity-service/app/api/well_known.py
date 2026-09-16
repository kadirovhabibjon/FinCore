from fastapi import APIRouter

from app.core.jwt_keys import build_jwks

# `.well-known/*` is a standard well-known URI (RFC 8615), conventionally
# unversioned and outside `/api/v1` — kept as its own router for that
# reason rather than living under app/api/v1/.
router = APIRouter(tags=["jwks"])


@router.get("/.well-known/jwks.json")
async def jwks() -> dict:
    return build_jwks()
