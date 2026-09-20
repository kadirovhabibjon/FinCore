from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "fraud-service"

    # postgresql+asyncpg://user:password@host:port/fraud_db
    database_url: str

    # Shared secret for /internal/* endpoints (Section 19).
    internal_service_token: str

    # Rule thresholds (spec Section 12's worked example). Kept as
    # settings, not constants, so they can be tuned without a code
    # change — but the *weights* a triggered rule adds to the score stay
    # in app/services/rules.py: those are part of each rule's identity,
    # not environment config.
    large_amount_threshold_minor: int = 500_000_00

    high_frequency_window_seconds: int = 60
    high_frequency_max_checks: int = 5

    repeated_failures_window_seconds: int = 3600
    repeated_failures_max_count: int = 3


settings = Settings()  # type: ignore[call-arg]
