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


settings = Settings()
