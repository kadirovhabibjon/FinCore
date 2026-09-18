from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "ledger-service"

    # postgresql+asyncpg://user:password@host:port/ledger_db
    database_url: str

    # Where identity-service publishes its public key (Section 5) — no
    # default: pointing this at the wrong place should fail loudly via a
    # missing .env value, not silently via a wrong built-in default.
    identity_service_jwks_url: str
    jwt_issuer: str = "fincore-identity-service"

    # Shared secret for /internal/* endpoints (Section 19). Required, no
    # default, same reasoning as jwt_private_key in identity-service: a
    # service must never boot with an implicit internal credential.
    internal_service_token: str

    # Reconciliation job (spec Section 8.4, ADR-0002): how often the
    # background loop independently re-verifies the ledger's invariants.
    reconciliation_interval_seconds: float = 300.0


settings = Settings()  # type: ignore[call-arg]
