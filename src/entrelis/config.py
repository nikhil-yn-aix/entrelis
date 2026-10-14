"""process settings read from the environment and an optional .env file."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """connection urls and credentials for the graph store and telemetry."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    falkordb_url: str = Field(
        default="redis://localhost:6379", validation_alias="ENTRELIS_FALKORDB_URL"
    )
    falkordb_password: SecretStr = Field(
        default=SecretStr(""), validation_alias="FALKORDB_PASSWORD"
    )
    falkordb_rw_password: SecretStr = Field(
        default=SecretStr(""), validation_alias="FALKORDB_RW_PASSWORD"
    )
    falkordb_ro_password: SecretStr = Field(
        default=SecretStr(""), validation_alias="FALKORDB_RO_PASSWORD"
    )
    otel_endpoint: str = Field(
        default="http://localhost:4318", validation_alias="ENTRELIS_OTEL_ENDPOINT"
    )
