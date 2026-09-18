from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "payment-service"

    # postgresql+asyncpg://user:password@host:port/payment_db
    database_url: str

    # For verifying end-user bearer tokens on public endpoints (Section 5).
    identity_service_jwks_url: str
    jwt_issuer: str = "fincore-identity-service"

    # Shared secret payment-service sends when calling ledger-service's
    # /internal/* API (Section 19). Must match ledger-service's own
    # INTERNAL_SERVICE_TOKEN.
    internal_service_token: str

    ledger_service_base_url: str
    ledger_service_timeout_seconds: float = 5.0

    fraud_service_base_url: str
    fraud_service_timeout_seconds: float = 0.3

    # Fail-open/fail-closed threshold when fraud-service is unreachable
    # (spec Section 12): amounts at or under this are ALLOWed (flagged);
    # amounts over it go to REVIEW instead of blocking the saga outright.
    # A single minor-units figure, not per-currency, is a deliberate v1
    # simplification — UZS and USD share the same minor-unit exponent for
    # now (ADR-0001), so this doesn't yet need to be currency-aware.
    fraud_fail_open_limit_minor: int = 100_000_00

    # Recovery worker (spec Section 10.1): a background loop that retries
    # transfers left PROCESSING by an unknown ledger outcome.
    recovery_worker_interval_seconds: float = 30.0
    recovery_worker_stuck_after_seconds: float = 60.0


settings = Settings()  # type: ignore[call-arg]
