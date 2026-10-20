from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Project Beacon"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-this-in-production"

    # Auth
    dev_api_key: str = "bkn_dev_change_me_in_production"
    allow_unsigned_webhooks: bool = True

    database_url: str = "postgresql+asyncpg://beacon:beacon_secret@localhost:5432/beacon"
    database_url_sync: str = "postgresql://beacon:beacon_secret@localhost:5432/beacon"
    redis_url: str = "redis://localhost:6379/0"

    max_upload_size_mb: int = 50
    allowed_extensions: str = "csv,xlsx,xls"

    data_retention_days: int = 365
    anonymize_on_export: bool = True

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [ext.strip().lower() for ext in self.allowed_extensions.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
