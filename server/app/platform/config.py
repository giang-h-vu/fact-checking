from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_host: str = ""
    ollama_model: str = ""

    google_api_key: str = ""
    google_cse_id: str = ""
    bing_api_key: str = ""

    database_url: str = ""

    http_timeout_seconds: float = 15.0
    max_concurrent_fetches: int = 5

    cors_origins: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
