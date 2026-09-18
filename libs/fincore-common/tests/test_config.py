import pytest
from pydantic import ValidationError

from fincore_common.config import BaseServiceSettings


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    # BaseServiceSettings looks for a `.env` in the current directory; run
    # from an empty tmp dir so these tests never pick up a real one.
    monkeypatch.chdir(tmp_path)


def test_service_name_is_required() -> None:
    with pytest.raises(ValidationError):
        BaseServiceSettings()


def test_defaults_when_only_service_name_given() -> None:
    settings = BaseServiceSettings(service_name="identity-service")

    assert settings.service_name == "identity-service"
    assert settings.environment == "local"
    assert settings.log_level == "INFO"
    assert settings.otel_exporter_otlp_endpoint == "http://localhost:4318"


def test_environment_variable_overrides_default(monkeypatch) -> None:
    monkeypatch.setenv("SERVICE_NAME", "ledger-service")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = BaseServiceSettings()

    assert settings.service_name == "ledger-service"
    assert settings.log_level == "DEBUG"


def test_unknown_fields_are_ignored() -> None:
    class ServiceSettings(BaseServiceSettings):
        pass

    settings = ServiceSettings(service_name="fraud-service", some_unrelated_key="x")

    assert settings.service_name == "fraud-service"
    assert not hasattr(settings, "some_unrelated_key")


def test_subclass_can_add_its_own_fields() -> None:
    class IdentitySettings(BaseServiceSettings):
        database_url: str

    settings = IdentitySettings(
        service_name="identity-service",
        database_url="postgresql+asyncpg://user:pass@localhost/identity_db",
    )

    assert settings.database_url.startswith("postgresql+asyncpg://")
