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

    # How long a session survives without being used. Every refresh
    # issues a new token valid for this long, so the window slides while
    # the customer is active and closes once they stop: someone who walks
    # away from a device without signing out is not still signed in the
    # next day. Must exceed the access-token TTL, since an active client
    # only refreshes when its access token runs out.
    refresh_token_ttl_seconds: int = 60 * 30
    # However active, a session ends this long after sign-in.
    session_max_lifetime_seconds: int = 60 * 60 * 12

    # Browser clients (the frontend, ADR-0006) opt into receiving the
    # refresh token as an httpOnly cookie instead of in the JSON body, by
    # sending `X-Refresh-Token-Transport: cookie`. `Secure` should only
    # be switched off for plain-http access from something other than
    # localhost, which browsers treat as a secure context anyway.
    refresh_cookie_name: str = "fincore_refresh"
    refresh_cookie_path: str = "/api/v1/auth"
    refresh_cookie_secure: bool = True

    # Password reset: a 6-digit code emailed to the account's address.
    # SMTP_HOST empty means "not configured": the reset endpoints answer
    # 503 instead of pretending a code was sent. For Gmail: host
    # smtp.gmail.com, port 587, an app password (scripts/set-smtp.sh).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    # The From address; defaults to the username when empty.
    smtp_from: str = ""
    smtp_timeout_seconds: float = 15.0
    password_reset_code_ttl_seconds: int = 600
    # Wrong guesses allowed against one code before it stops working.
    password_reset_max_attempts: int = 5
    # Codes one account may request per hour (each is an email sent).
    password_reset_max_requests_per_hour: int = 5

    # Shared secret for /internal/* (spec Section 19): payment-service
    # sends it to look up a transfer recipient's name. Empty means no
    # caller is trusted: the internal API then rejects every request,
    # rather than this service refusing to start for want of a setting
    # that nothing about signing in depends on.
    internal_service_token: str = ""

    # Outbox relay (spec Section 14.1): account events (registration,
    # status and role changes) go to audit-service through Kafka, written
    # in the same transaction as the change so none can be lost.
    kafka_bootstrap_servers: str = "localhost:9094"
    users_topic: str = "users"
    outbox_relay_interval_seconds: float = 5.0
    outbox_relay_batch_size: int = 100


# Required fields (database_url, jwt_private_key) have no defaults on
# purpose — pydantic-settings fills them from the environment/.env at
# runtime, which mypy's static call-signature check can't see. This is
# the documented pydantic-settings pattern for that mismatch.
settings = Settings()  # type: ignore[call-arg]
