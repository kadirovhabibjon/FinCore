from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


async def test_jwks_endpoint_returns_the_public_key() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/.well-known/jwks.json")

    assert response.status_code == 200
    body = response.json()
    assert body["keys"][0]["kid"] == settings.jwt_key_id
