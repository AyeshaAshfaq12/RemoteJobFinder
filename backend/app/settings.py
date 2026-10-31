"""Runtime settings. Everything comes from environment variables (prefix RJF_)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RJF_", env_file=".env", extra="ignore")

    env: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"

    # Public origin: web app and API share one domain, path-routed (decided 2026-10-29).
    # It is the OAuth issuer and the base of the MCP resource URL (<origin>/mcp).
    public_origin: str = "http://localhost:3000"

    # HMAC key for signed pending-authorization blobs and similar short-lived tokens.
    secret_key: SecretStr = Field(default=SecretStr("dev-only-change-me"))

    # Email codes via generic SMTP (decided 2026-10-29). No host = log to console (local only).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "Remote Job Finder <no-reply@localhost>"
    smtp_starttls: bool = True

    # Extra Host headers accepted on /mcp (e.g. a tunnel hostname), comma-separated in env JSON.
    extra_allowed_hosts: list[str] = []

    # Web sessions
    session_cookie: str = "rjf_session"
    session_ttl_days: int = 30

    # Postgres: async URL for the app, sync URL for Alembic and Celery tasks.
    database_url: str = "postgresql+asyncpg://rjf:rjf@localhost:5432/rjf"
    database_url_sync: str = "postgresql+psycopg://rjf:rjf@localhost:5432/rjf"

    redis_url: str = "redis://localhost:6379/0"

    # Object storage (S3-compatible)
    s3_endpoint_url: str | None = None
    s3_bucket: str = "rjf"
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None

    # AES-256-GCM keys for profiles.data: "<version>:<base64 32-byte key>,..." newest first.
    profile_keys: SecretStr = Field(default=SecretStr(""))

    # Security limits
    max_body_bytes: int = 2 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
