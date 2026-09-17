from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "ledger-service"

    # postgresql+asyncpg://user:password@host:port/ledger_db
    database_url: str


settings = Settings()  # type: ignore[call-arg]
