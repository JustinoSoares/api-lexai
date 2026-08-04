from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "api-lexai"
    debug: bool = False
    log_level: str = "INFO"

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lexai"

    groq_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.3

    web_search_enabled: bool = True

    rate_limit_enabled: bool = False
    rate_limit_max_requests: int = 10
    rate_limit_window_seconds: int = 60
    rate_limit_user_header: str = "X-User-Id"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
