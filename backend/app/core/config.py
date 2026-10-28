"""Application settings, loaded from environment variables (and an optional .env file).

In Docker the values are injected by compose; for local development the root `.env`
(or `backend/.env`) is picked up automatically.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Isofactu API"
    app_version: str = "0.1.0"
    app_env: str = Field(default="dev", description="dev | test | prod")
    debug: bool = False

    database_url: str = Field(
        default="postgresql+psycopg://app:app@127.0.0.1:5433/isofactu",
        description="SQLAlchemy URL. The psycopg (v3) async driver is used.",
    )
    db_echo: bool = False

    # Directory with the built frontend (Vite output). Served as a SPA when present.
    public_dir: Path = PROJECT_DIR / "public"

    # Comma separated list of allowed CORS origins (only needed when the SPA is served
    # from a different origin, e.g. the Vite dev server).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        """Accept plain `postgresql://` / `postgres://` URLs and pin the async driver."""
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
