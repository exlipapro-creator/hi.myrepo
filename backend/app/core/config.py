"""
hi.myrepo - Core Configuration

All configuration is loaded from environment variables.
Secrets are NEVER hardcoded.
"""

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "hi.myrepo"
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    app_debug: bool = False
    app_secret_key: str = "change-me"
    app_port: int = 8000
    app_host: str = "0.0.0.0"

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = ""
    database_ssl: bool = True
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ── Supabase ─────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # ── AI Providers ─────────────────────────────────────────────────────
    gemini_api_key: str = ""
    openai_api_key: str = ""
    groq_api_key: str = ""
    ai_default_provider: str = "gemini"
    ai_fallback_enabled: bool = True
    ai_max_retries: int = 3
    ai_request_timeout: int = 30

    # ── Webhooks ─────────────────────────────────────────────────────────
    github_webhook_secret: str = ""
    vercel_webhook_secret: str = ""
    custom_webhook_secret: str = ""

    # ── Authentication ───────────────────────────────────────────────────
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # ── Rate Limiting ────────────────────────────────────────────────────
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 10

    # ── Heartbeat ────────────────────────────────────────────────────────
    heartbeat_interval_seconds: int = 60
    heartbeat_timeout_seconds: int = 10
    heartbeat_worker_enabled: bool = True

    # ── SSRF Protection ──────────────────────────────────────────────────
    allowed_hosts: str = "localhost,127.0.0.1"
    block_private_networks: bool = True

    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "json"

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnvironment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.app_env == AppEnvironment.TESTING

    @property
    def async_database_url(self) -> str:
        """Convert postgresql:// to postgresql+asyncpg:// for async usage."""
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def sync_database_url(self) -> str:
        """Database URL for synchronous usage (migrations)."""
        return self.database_url

    @property
    def available_ai_providers(self) -> list[str]:
        """List of AI providers with configured API keys."""
        providers = []
        if self.gemini_api_key:
            providers.append("gemini")
        if self.openai_api_key:
            providers.append("openai")
        if self.groq_api_key:
            providers.append("groq")
        return providers


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
