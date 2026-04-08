"""Application settings from environment files.

**Which file loads** is chosen only from real process environment (set in the shell
before starting uvicorn — not from inside the dotenv file):

- ``FRANCHISE_DOTENV`` — ``local`` | ``dev`` | ``prod`` → loads ``.env.local``,
  ``.env.dev``, or ``.env.prod`` under the repo root. Default: ``local``.
- ``FRANCHISE_DOTENV_PATH`` — optional absolute or repo-relative path to an env file;
  when set, it wins over ``FRANCHISE_DOTENV``.

The selected file **must exist**; otherwise import fails with a clear error.

Examples::

    FRANCHISE_DOTENV=dev uvicorn apps.api.src.main:app --reload
    FRANCHISE_DOTENV=prod uvicorn apps.api.src.main:app

All variables in that file are **required** for the app: missing or empty values
raise ``ValidationError`` when ``Settings`` is built.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: foundation/config/settings.py -> parents[2] == franchise_billing/
_ROOT = Path(__file__).resolve().parents[2]

_PROFILE_FILES: dict[str, str] = {
    "local": ".env.local",
    "dev": ".env.dev",
    "prod": ".env.prod",
}


def _resolve_dotenv_path() -> Path:
    raw_override = os.environ.get("FRANCHISE_DOTENV_PATH", "").strip()
    if raw_override:
        p = Path(raw_override)
        return p if p.is_absolute() else (_ROOT / p)

    profile = os.environ.get("FRANCHISE_DOTENV", "local").strip().lower()
    if profile not in _PROFILE_FILES:
        allowed = ", ".join(sorted(_PROFILE_FILES))
        raise RuntimeError(
            f"FRANCHISE_DOTENV={profile!r} is invalid; use one of: {allowed}. "
            "Or set FRANCHISE_DOTENV_PATH to a specific env file.")
    return _ROOT / _PROFILE_FILES[profile]


_DOTENV_PATH = _resolve_dotenv_path()
if not _DOTENV_PATH.is_file():
    hint = ""
    legacy = _ROOT / ".env"
    if legacy.is_file():
        hint = (f" Found {legacy} — copy or rename it to {_DOTENV_PATH.name}, "
                "or set FRANCHISE_DOTENV_PATH.")
    raise RuntimeError(f"Env file not found: {_DOTENV_PATH}.{hint} "
                       "Copy from .env.example if needed.")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_DOTENV_PATH,
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


def resolved_dotenv_path() -> Path:
    """Absolute path to the env file used by ``Settings`` (for logging / support)."""
    return _DOTENV_PATH


@lru_cache
def get_settings() -> Settings:
    return Settings()
