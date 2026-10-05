import logging
from dataclasses import dataclass
from uuid import UUID

import httpx
from fincore_common import async_client

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserInfo:
    first_name: str
    last_name: str
    status: str


class IdentityUnavailableError(Exception):
    """identity-service couldn't answer."""


class IdentityClient:
    """identity-service's internal API (shared-secret authenticated):
    just enough about a user to show a sender who they are paying."""

    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._internal_token = internal_token
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def get_user(self, user_id: UUID) -> UserInfo | None:
        try:
            async with async_client(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"/internal/v1/users/{user_id}",
                    headers={"X-Internal-Token": self._internal_token},
                )
        except httpx.RequestError as exc:
            raise IdentityUnavailableError(str(exc)) from exc

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            # Includes 403: a token identity-service doesn't accept is a
            # deployment fault, reported as "unavailable", not as "no
            # such recipient".
            raise IdentityUnavailableError(f"identity-service returned {response.status_code}")
        data = response.json()
        return UserInfo(
            first_name=data["first_name"], last_name=data["last_name"], status=data["status"]
        )


identity_client = IdentityClient(
    base_url=settings.identity_service_base_url,
    internal_token=settings.internal_service_token,
    timeout_seconds=settings.identity_service_timeout_seconds,
)
