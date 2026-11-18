"""Application settings, loaded from environment variables (and an optional .env file).

In Docker the values are injected by compose; for local development the root `.env`
(or `backend/.env`) is picked up automatically.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent

# Placeholder used when SECRET_KEY is not configured. Fine for development, refused in prod.
INSECURE_SECRET_KEY = "dev-only-insecure-secret-key-change-me"


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
    # Level of the application loggers (`app.*`): DEBUG | INFO | WARNING | ERROR
    log_level: str = "INFO"

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

    # -- authentication -----------------------------------------------------------------
    # Signs the session cookie. MUST be set to a long random value in production.
    secret_key: str = INSECURE_SECRET_KEY
    session_cookie_name: str = "isofactu_session"
    session_ttl_hours: int = Field(default=24 * 7, ge=1)
    # `Secure` flag of the session cookie (HTTPS only). Defaults to on in prod, off elsewhere.
    session_cookie_secure: bool | None = None
    # bcrypt work factor. Lowered in the test-suite to keep it fast.
    password_hash_rounds: int = Field(default=12, ge=4, le=31)

    # -- e-mail -------------------------------------------------------------------------
    # Public URL of the application, used to build the links sent by e-mail.
    app_public_url: str = "http://localhost:8000"
    # Leave SMTP_HOST empty to log outgoing e-mails instead of sending them.
    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    smtp_timeout: float = 10.0
    mail_from: str = ""

    # -- secrets stored in the database (e.g. the tenants' AI API keys) --------------------
    # Comma-separated Fernet keys: the first encrypts, all decrypt (rotation). Generate one
    # with `python -m app.cli secrets generate-key`. Empty: a key derived from SECRET_KEY.
    encryption_keys: str = Field(default="", repr=False)

    # -- PDF import of received invoices ---------------------------------------------------
    # The AI vendor, model and API key are set by each tenant in its settings (stored in
    # the database, the key encrypted); the server only bounds the work.
    llm_timeout: float = Field(default=120.0, gt=0)
    invoice_pdf_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1)

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        """Accept plain `postgresql://` / `postgres://` URLs and pin the async driver."""
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @field_validator("app_public_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("secret_key")
    @classmethod
    def _empty_secret_is_unset(cls, value: str) -> str:
        return value.strip() or INSECURE_SECRET_KEY

    @field_validator("encryption_keys")
    @classmethod
    def _check_encryption_keys(cls, value: str) -> str:
        from cryptography.fernet import Fernet

        for key in (part.strip() for part in value.split(",") if part.strip()):
            try:
                Fernet(key)
            except ValueError as exc:
                raise ValueError(
                    "ENCRYPTION_KEYS must hold Fernet keys (32 url-safe base64-encoded bytes); "
                    "generate one with `python -m app.cli secrets generate-key`"
                ) from exc
        return value

    @model_validator(mode="after")
    def _refuse_insecure_production(self) -> "Settings":
        if self.app_env == "prod" and self.secret_key == INSECURE_SECRET_KEY:
            raise ValueError("SECRET_KEY must be set to a random value when APP_ENV=prod")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cookie_secure(self) -> bool:
        if self.session_cookie_secure is None:
            return self.app_env == "prod"
        return self.session_cookie_secure

    @property
    def mail_enabled(self) -> bool:
        return bool(self.smtp_host)

    @property
    def encryption_key_list(self) -> list[str]:
        return [key.strip() for key in self.encryption_keys.split(",") if key.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
