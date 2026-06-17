from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_host: str = ""
    ollama_model: str = ""
    ollama_num_ctx: int = 8192

    brave_api_key: str = ""

    database_url: str = ""

    http_timeout_seconds: float = 20.0
    max_concurrent_fetches: int = 3
    search_results_per_query: int = 3

    cors_origins: str = ""

    # --- Auth (Google OAuth + JWT sessions) ---------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    # The callback URL registered with Google; the browser is sent here after consent.
    oauth_redirect_uri: str = "http://localhost:5173/api/v1/auth/google/callback"
    # Where the backend redirects the browser after a successful login.
    frontend_url: str = "http://localhost:5173/"

    # Signs the short-lived access-token JWT.
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    # Signs the Starlette session that holds Authlib's OAuth state/nonce.
    session_secret: str = ""

    access_token_ttl_seconds: int = 900  # 15 minutes
    refresh_token_ttl_seconds: int = 1_209_600  # 14 days

    # Cookies: Secure should be True behind HTTPS in production.
    cookie_secure: bool = False
    cookie_samesite: str = "strict"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
