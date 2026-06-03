from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TGServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="Universe Telegram Service", alias="TG_SERVICE_APP_NAME")
    app_debug: bool = Field(default=False, alias="TG_SERVICE_APP_DEBUG")
    cors_allow_origins: str = Field(default="http://localhost:3100", alias="CORS_ALLOW_ORIGINS")

    service_token_secret: str = Field(default="change-service-secret", alias="SERVICE_TOKEN_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    backend_api_base_url: str = Field(default="http://backend-api:8000/api/v1", alias="BACKEND_API_BASE_URL")
    backend_timeout_seconds: int = Field(default=10, alias="TG_BACKEND_TIMEOUT_SECONDS")

    tg_bot_token: str | None = Field(default=None, alias="TG_BOT_TOKEN")
    tg_bot_username: str = Field(default="universe_bot", alias="TG_BOT_USERNAME")
    tg_polling_enabled: bool = Field(default=True, alias="TG_POLLING_ENABLED")
    tg_delete_webhook_on_start: bool = Field(default=True, alias="TG_DELETE_WEBHOOK_ON_START")
    tg_drop_pending_updates_on_start: bool = Field(default=False, alias="TG_DROP_PENDING_UPDATES_ON_START")
    tg_init_data_ttl_seconds: int = Field(default=3600, alias="TG_INIT_DATA_TTL_SECONDS")

    student_app_url: str = Field(default="http://localhost:3100", alias="STUDENT_APP_URL")


@lru_cache
def get_settings() -> TGServiceSettings:
    return TGServiceSettings()
