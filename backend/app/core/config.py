from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), str(_BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    app_name: str = "Mira"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-this-in-production"
    # When true, runs `alembic upgrade head` on API startup (safe for additive migrations).
    auto_migrate: bool = True

    # Auth
    dev_api_key: str = "bkn_dev_change_me_in_production"
    mira_admin_secret: str | None = None
    allow_unsigned_webhooks: bool = True

    # Model training guards (False em produção)
    allow_force_train: bool = True
    allow_force_activate: bool = True

    # Composio integration (fail-closed; no SDK calls until explicitly activated)
    composio_enabled: bool = False
    composio_api_key: str | None = None
    composio_identity_secret: str | None = None
    composio_callback_url: str | None = None
    composio_allowed_toolkits: str = ""
    # Optional API credential; only used by server-side onboarding enrichment.
    firecrawl_api_key: str | None = None
    # Tool execution remains explicitly disabled until Wave 3.1 is validated.
    composio_tool_execution_enabled: bool = False

    # Scoring
    shap_on_batch: bool = False
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    mira_public_url: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://beacon:beacon_secret@127.0.0.1:5433/beacon"
    database_url_sync: str = "postgresql://beacon:beacon_secret@127.0.0.1:5433/beacon"
    redis_url: str = "redis://localhost:6379/0"
    model_storage_dir: str = str(_REPO_ROOT / "data" / "model_artifacts")
    retention_queue_name: str = "beacon:retention:jobs"
    retention_job_ttl_seconds: int = 86400
    retention_max_attempts: int = 3
    retention_retry_backoff_seconds: int = 5
    retention_dead_letter_queue_name: str = "beacon:retention:dead-letter"
    jacad_queue_name: str = "beacon:jacad:jobs"
    jacad_job_ttl_seconds: int = Field(default=604800, ge=3600, le=2592000)
    jacad_max_attempts: int = Field(default=3, ge=1, le=8)
    jacad_retry_backoff_seconds: int = Field(default=15, ge=1, le=3600)
    jacad_detail_refresh_hours: int = Field(default=24, ge=1, le=168)
    jacad_sync_concurrency: int = Field(default=5, ge=1, le=12)
    sponte_queue_name: str = "beacon:sponte:jobs"
    sponte_job_ttl_seconds: int = Field(default=604800, ge=3600, le=2592000)
    sponte_max_attempts: int = Field(default=3, ge=1, le=8)
    sponte_retry_backoff_seconds: int = Field(default=15, ge=1, le=3600)
    sponte_sync_concurrency: int = Field(default=5, ge=1, le=12)
    sponte_requests_per_minute: int = Field(default=900, ge=1, le=1000)
    sponte_global_requests_per_second: int = Field(default=5, ge=1, le=15)


    max_upload_size_mb: int = 50
    allowed_extensions: str = "csv,xlsx,xls"

    data_retention_days: int = 365
    anonymize_on_export: bool = True
    intervention_log_retention_days: int = Field(default=180, ge=90, le=180)
    engagement_timezone: str = "America/Sao_Paulo"
    engagement_response_window_hours: int = Field(default=72, ge=24, le=168)
    engagement_history_days: int = Field(default=90, ge=30, le=365)
    engagement_sweep_interval_seconds: int = Field(default=3600, ge=60, le=86400)
    engagement_channel_suppression_hours: int = Field(default=72, ge=1, le=720)

    # Estimated unit costs in BRL. Zero means not configured.
    agents_cost_per_whatsapp_message_brl: float = Field(default=0.0, ge=0.0, le=100.0)
    agents_cost_per_email_message_brl: float = Field(default=0.0, ge=0.0, le=100.0)
    agents_cost_per_sms_message_brl: float = Field(default=0.0, ge=0.0, le=100.0)

    # Dispatch Platform — all defaults fail closed. Worker is separate from API.
    dispatch_worker_enabled: bool = False
    dispatch_live_enabled: bool = False
    dispatch_live_tenants: str = ""
    dispatch_live_channels: str = ""
    # Explicit allowlist for verifiable permission evidence source identifiers.
    dispatch_trusted_authorization_sources: str = ""
    dispatch_webhook_secret: str | None = None
    dispatch_resend_webhook_secret: str | None = None
    dispatch_twilio_callback_url: str | None = None
    dispatch_contact_encryption_key: str | None = None

    # Agentes de retencao (orquestrador + canais WhatsApp/E-mail/SMS)
    agents_dry_run_default: bool = True
    agents_min_hours_between_contact: int = 48
    agents_max_contacts_per_week: int = 3
    agents_provider_timeout_seconds: float = 15.0
    agents_rate_limit_enabled: bool = True
    agents_rate_limit_per_tenant_per_minute: int = 60
    agents_rate_limit_per_channel_per_minute: int = 60
    agents_rate_limit_per_provider_per_minute: int = 120
    agents_circuit_breaker_failure_threshold: int = 5
    agents_circuit_breaker_open_seconds: int = 60
    agents_provider_latency_threshold_ms: int = Field(default=2500, ge=100, le=60000)
    agents_provider_backpressure_factor: float = Field(default=0.5, gt=0.0, le=1.0)
    agents_idempotency_ttl_seconds: int = Field(default=86400, ge=300, le=604800)
    whatsapp_provider_order: str = "waha,evolution"

    evolution_api_url: str | None = None
    evolution_api_key: str | None = None
    evolution_instance: str | None = None

    waha_api_url: str | None = None
    waha_api_key: str | None = None
    waha_session: str = "default"

    resend_api_key: str | None = None
    email_from: str | None = None

    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from: str | None = None

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [ext.strip().lower() for ext in self.allowed_extensions.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
