"""Test doubles for the two things assistant-service talks to: the Claude
API (a scripted httpx2 transport behind the real SDK, so request
building is exercised for real) and FinCore's own APIs (an httpx mock)."""

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import anthropic
import httpx
import httpx2
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fincore_common import JWTVerifier

from app.core import auth as auth_module
from app.core.config import settings


def message(*content: dict[str, Any], stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": settings.assistant_model,
        "content": list(content),
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value}


def tool_use(tool_id: str, name: str, **arguments: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": arguments}


class FakeClaude:
    """Answers each Messages request with the next scripted response and
    records every request body."""

    def __init__(self, *responses: dict[str, Any] | tuple[int, dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        scripted = self._responses.pop(0)
        status, body = scripted if isinstance(scripted, tuple) else (200, scripted)
        return httpx2.Response(status, json=body)

    def client(self) -> anthropic.AsyncAnthropic:
        return anthropic.AsyncAnthropic(
            api_key="test-key",
            max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(
                transport=httpx2.MockTransport(self._handle)
            ),
        )


def fincore_api(
    routes: dict[str, Callable[[httpx.Request], httpx.Response]],
) -> httpx.MockTransport:
    """FinCore's public APIs, keyed "GET /path"; records nothing, 404s the rest."""

    def handle(request: httpx.Request) -> httpx.Response:
        handler = routes.get(f"{request.method} {request.url.path}")
        if handler is None:
            return httpx.Response(404, json={"title": "Not Found"})
        return handler(request)

    return httpx.MockTransport(handle)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def install_token_issuer(monkeypatch: Any) -> Callable[[UUID], str]:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    jwks = {
        "keys": [{"kty": "OKP", "crv": "Ed25519", "x": _b64url(public), "kid": "k", "alg": "EdDSA"}]
    }
    jwks_app = FastAPI()

    @jwks_app.get("/.well-known/jwks.json")
    async def _jwks() -> dict[str, Any]:
        return jwks

    monkeypatch.setattr(
        auth_module,
        "jwt_verifier",
        JWTVerifier(
            jwks_url="http://identity/.well-known/jwks.json",
            issuer=settings.jwt_issuer,
            transport=httpx.ASGITransport(app=jwks_app),
        ),
    )

    def issue(user_id: UUID) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": str(user_id),
            "iss": settings.jwt_issuer,
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "roles": ["USER"],
        }
        return jwt.encode(claims, private_pem, algorithm="EdDSA", headers={"kid": "k"})

    return issue
