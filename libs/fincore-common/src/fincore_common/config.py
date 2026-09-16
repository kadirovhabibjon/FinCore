from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Common configuration every FinCore service extends with its own fields.

    Reads from a `.env` file in the service's working directory, then from
    the process environment (which takes precedence). Unknown keys are
    ignored so a shared `.env` cannot break a service that doesn't use one
    of its fields.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str
    environment: str = "local"
    log_level: str = "INFO"
