from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="Universe Backend API", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    app_timezone: str = Field(default="Europe/Moscow", alias="APP_TIMEZONE")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    cors_allow_origins: str = Field(default="http://localhost:3000", alias="CORS_ALLOW_ORIGINS")
    cors_allow_origin_regex: str | None = Field(default=None, alias="CORS_ALLOW_ORIGIN_REGEX")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/universe",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    jwt_secret: str = Field(default="change-me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=20, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=14, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    service_token_secret: str = Field(default="change-service-secret", alias="SERVICE_TOKEN_SECRET")
    tg_service_base_url: str = Field(default="http://tg-service:8080", alias="TG_SERVICE_BASE_URL")
    tg_service_timeout_seconds: int = Field(default=5, alias="TG_SERVICE_TIMEOUT_SECONDS")
    tg_bot_username: str = Field(default="universe_bot", alias="TG_BOT_USERNAME")

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_api_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_API_BASE_URL")
    openrouter_timeout_seconds: int = Field(default=20, alias="OPENROUTER_TIMEOUT_SECONDS")
    faq_assistant_model: str = Field(
        default="openai/gpt-4.1-mini",
        alias="FAQ_ASSISTANT_MODEL",
    )
    faq_embeddings_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        alias="FAQ_EMBEDDINGS_MODEL",
    )
    faq_embeddings_cache_dir: str = Field(
        default="/var/lib/universe/faq-models",
        alias="FAQ_EMBEDDINGS_CACHE_DIR",
    )
    faq_source_dir: str = Field(default="data", alias="FAQ_SOURCE_DIR")
    faq_index_dir: str = Field(default="/var/lib/universe/faq-index", alias="FAQ_INDEX_DIR")
    faq_assistant_enabled: bool = Field(default=True, alias="FAQ_ASSISTANT_ENABLED")
    faq_ai_top_k: int = Field(default=4, alias="FAQ_AI_TOP_K")
    faq_history_ttl_seconds: int = Field(default=86400, alias="FAQ_HISTORY_TTL_SECONDS")
    faq_history_max_messages: int = Field(default=8, alias="FAQ_HISTORY_MAX_MESSAGES")

    attachments_dir: str = Field(default="/var/lib/universe/attachments", alias="ATTACHMENTS_DIR")
    attachments_max_size_mb: int = Field(default=10, alias="ATTACHMENTS_MAX_SIZE_MB")
    ai_imports_dir: str = Field(default="/var/lib/universe/ai-imports", alias="AI_IMPORTS_DIR")
    ai_import_max_size_mb: int = Field(default=20, alias="AI_IMPORT_MAX_SIZE_MB")
    ai_import_model: str = Field(default="openai/gpt-4.1-mini", alias="AI_IMPORT_MODEL")
    ai_import_timeout_seconds: int = Field(default=60, alias="AI_IMPORT_TIMEOUT_SECONDS")
    ai_import_max_pages: int = Field(default=20, alias="AI_IMPORT_MAX_PAGES")
    ai_import_max_chars: int = Field(default=40000, alias="AI_IMPORT_MAX_CHARS")

    rate_limit_tg_per_minute: int = Field(default=60, alias="RATE_LIMIT_TG_PER_MINUTE")
    audit_retention_months: int = Field(default=24, alias="AUDIT_RETENTION_MONTHS")

    default_late_threshold_minutes: int = Field(default=20, alias="DEFAULT_LATE_THRESHOLD_MINUTES")
    default_window_start_offset_minutes: int = Field(
        default=-5,
        alias="DEFAULT_WINDOW_START_OFFSET_MINUTES",
    )
    default_window_duration_minutes: int = Field(default=20, alias="DEFAULT_WINDOW_DURATION_MINUTES")
    teacher_correction_window_days: int = Field(default=3, alias="TEACHER_CORRECTION_WINDOW_DAYS")
    qr_dynamic_slot_seconds: int = Field(default=3, alias="QR_DYNAMIC_SLOT_SECONDS")
    qr_dynamic_grace_slots: int = Field(default=2, alias="QR_DYNAMIC_GRACE_SLOTS")
    qr_dynamic_token_secret: str | None = Field(default=None, alias="QR_DYNAMIC_TOKEN_SECRET")

    biometric_signature_max_drift_seconds: int = Field(default=30, alias="BIOMETRIC_SIGNATURE_MAX_DRIFT_SECONDS")
    biometric_nonce_ttl_seconds: int = Field(default=90, alias="BIOMETRIC_NONCE_TTL_SECONDS")
    biometric_public_enabled: bool = Field(default=True, alias="BIOMETRIC_PUBLIC_ENABLED")

    default_escalation_unexcused_absences: int = Field(
        default=3,
        alias="DEFAULT_ESCALATION_UNEXCUSED_ABSENCES",
    )
    default_escalation_lates: int = Field(default=4, alias="DEFAULT_ESCALATION_LATES")
    default_escalation_min_rating: int = Field(default=60, alias="DEFAULT_ESCALATION_MIN_RATING")


@lru_cache
def get_settings() -> Settings:
    return Settings()
