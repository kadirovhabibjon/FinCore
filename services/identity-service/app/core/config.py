from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "identity-service"

    # postgresql+asyncpg://user:password@host:port/identity_db
    database_url: str

    # PEM-encoded Ed25519 private key. Required, no default: a service
    # must never boot with an implicit/dev-fallback signing key. Generate
    # with: openssl genpkey -algorithm ed25519
    jwt_private_key: str
    jwt_issuer: str = "fincore-identity-service"
    # Identifies which key signed a token, published in JWKS alongside the
    # public key so a future key rotation can run two keys side by side.
    jwt_key_id: str = "identity-2026-09"
    jwt_access_token_ttl_seconds: int = 900

    # 30 days — long-lived by design (that's the point of a refresh
    # token), which is exactly why it's rotated on every use and never
    # stored as anything but a hash.
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30

    # Browser clients (the frontend, ADR-0006) opt into receiving the
    # refresh token as an httpOnly cookie instead of in the JSON body, by
    # sending `X-Refresh-Token-Transport: cookie`. `Secure` should only
    # be switched off for plain-http access from something other than
    # localhost, which browsers treat as a secure context anyway.
    refresh_cookie_name: str = "fincore_refresh"
    refresh_cookie_path: str = "/api/v1/auth"
    refresh_cookie_secure: bool = True


# Required fields (database_url, jwt_private_key) have no defaults on
# purpose — pydantic-settings fills them from the environment/.env at
# runtime, which mypy's static call-signature check can't see. This is
# the documented pydantic-settings pattern for that mismatch.
settings = Settings()  # type: ignore[call-arg]
