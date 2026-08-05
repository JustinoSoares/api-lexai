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
    redis_url: str = "redis://localhost:6379/0"

    groq_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.3
    # Orçamento (chars) do texto de um diploma injetado como grounding.
    # 12000 preserva os artigos relevantes (verificado PAG/LGT) com ~40% menos
    # tokens que 20000; reduzir abaixo de ~8000 corta artigos relevantes da LGT.
    llm_ground_max_chars: int = 12000

    web_search_enabled: bool = True

    # Domínios jurídicos angolanos priorizados na busca web (JSON list).
    legal_whitelist_domains: list[str] = [
        "lex.ao",
        "diariodarepublica.ao",
        "governo.gov.ao",
        "parlamento.ao",
        "minjusdh.gov.ao",
        "tribunalsupremo.ao",
        "legis-palop.org",
        "lexlink.eu",
        "vlex.com",
        "consultorjuridico.com",
        "angola-forum.com",
    ]
    # Termos que reforçam a relevância de um resultado fora da whitelist (JSON list).
    legal_search_keywords: list[str] = [
        "lei", "decreto", "diploma", "constituição", "código civil",
        "código penal", "regulamento", "boletim oficial", "diário da república",
        "assembleia nacional", "ministério da justiça", "legislação",
    ]

    rate_limit_enabled: bool = False
    rate_limit_max_requests: int = 10
    rate_limit_window_seconds: int = 60
    rate_limit_user_header: str = "X-User-Id"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
