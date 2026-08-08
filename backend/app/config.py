from __future__ import annotations

import json
from pathlib import Path

from pydantic_settings import BaseSettings


_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    PG_HOST: str
    PG_PORT: int = 6543
    PG_USER: str
    PG_PASSWORD: str
    PG_DBNAME: str = "postgres"

    GOOGLE_API_KEY: str = ""
    GOOGLE_MODEL: str = "gemini-3.5-flash-lite"
    # Gemini rejects manually configured deadlines below 10 seconds.
    # This is only a failure ceiling; successful responses return immediately.
    GOOGLE_TIMEOUT_SECONDS: float = 10.0
    GOOGLE_RETRY_ATTEMPTS: int = 1
    CHAT_QUERY_CACHE_SECONDS: float = 15.0
    CHAT_PLAN_CACHE_SECONDS: float = 300.0
    CHAT_TEMPLATE_FALLBACK: bool = False

    MONGO_URI: str = "mongodb://localhost:27017"

    CORS_ORIGINS: str = '["http://localhost:3000"]'

    @property
    def cors_origins_list(self) -> list[str]:
        return json.loads(self.CORS_ORIGINS)

    @property
    def pg_dsn(self) -> str:
        return (
            f"postgresql://{self.PG_USER}:{self.PG_PASSWORD}"
            f"@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DBNAME}"
        )

    model_config = {"env_file": str(_ENV_FILE), "extra": "ignore"}


settings = Settings()
