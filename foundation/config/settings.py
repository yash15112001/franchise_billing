"""Application settings from environment.

**Local:** copy ``.env.example`` to ``.env`` at the repo root. You can keep values for
multiple targets in that one file and **comment or uncomment** lines to pick what is
active (dotenv only reads uncommented ``KEY=value`` lines).

**Deployment (Railway, etc.):** do not commit ``.env``. Set the same variables in the
host’s environment; if ``.env`` is absent, settings come only from the process
environment.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: foundation/config/settings.py -> parents[2] == franchise_billing/
_ROOT = Path(__file__).resolve().parents[2]
_DOTENV_FILE = _ROOT / ".env"
_ENV_FILE = _DOTENV_FILE if _DOTENV_FILE.is_file() else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Franchise Billing Platform"
    app_env: str = Field(
        ...,
        min_length=1,
        description="Deployment environment (e.g. development, production).",
    )
    api_prefix: str = Field(
        ...,
        min_length=1,
        description="URL prefix for HTTP routes and OpenAPI (e.g. /api/v1).",
    )
    database_url: str = Field(
        ...,
        min_length=1,
        description="SQLAlchemy database URL (e.g. postgresql+psycopg://...).",
    )
    bootstrap_admin_secret: str = Field(
        ...,
        min_length=32,
        description="Secret required for one-time main-admin bootstrap.",
    )
    jwt_secret_key: str = Field(
        ...,
        min_length=32,
        description="HS* signing key for JWT access tokens.",
    )
    jwt_algorithm: str = "HS512"


def resolved_dotenv_path() -> Path | None:
    """Path to ``.env`` when that file exists and is loaded; else ``None`` (env-only)."""
    return _ENV_FILE


@lru_cache
def get_settings() -> Settings:
    return Settings()
