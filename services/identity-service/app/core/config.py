from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "identity-service"

    # postgresql+asyncpg://user:password@host:port/identity_db
    database_url: str


settings = Settings()
