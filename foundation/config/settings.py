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
    whatsapp_meta_access_token: str = Field(
        ...,
        min_length=1,
        description="Access token for the WhatsApp Meta API proxy.",
    )
    whatsapp_meta_base_url: str = Field(
        default="https://crmapi.lifeweblink.com/api/meta",
        min_length=1,
        description="Base URL for WhatsApp Meta API proxy requests.",
    )
    whatsapp_meta_api_version: str = Field(
        default="v19.0",
        min_length=1,
        description="Meta Graph API version used by the WhatsApp API proxy.",
    )
    whatsapp_meta_waba_id: str = Field(
        ...,
        min_length=1,
        description="WhatsApp Business Account ID.",
    )
    whatsapp_meta_phone_number_id: str = Field(
        ...,
        min_length=1,
        description="WhatsApp sender phone number ID.",
    )
    whatsapp_meta_business_id: str = Field(
        ...,
        min_length=1,
        description="Meta Business ID.",
    )
    whatsapp_default_country_code: str = Field(
        default="+91",
        min_length=1,
        description="Default country code used when stored numbers omit it.",
    )
    whatsapp_template_name: str = Field(
        ...,
        min_length=1,
        description="Approved Meta WhatsApp template name used for proof sends.",
    )
    whatsapp_payment_reminder_template_name: str | None = Field(
        default=None,
        description="Approved Meta WhatsApp template name used for payment reminder sends.",
    )
    whatsapp_template_language_code: str = Field(
        default="en",
        min_length=1,
        description="Language code for the approved Meta WhatsApp templates.",
    )
    aws_access_key_id: str = Field(
        ...,
        min_length=1,
        description="AWS access key id for S3 access.",
    )
    aws_secret_access_key: str = Field(
        ...,
        min_length=1,
        description="AWS secret access key for S3 access.",
    )
    aws_region: str = Field(
        ...,
        min_length=1,
        description="AWS region for S3 operations.",
    )
    s3_bucket_name: str = Field(
        ...,
        min_length=1,
        description="S3 bucket name for invoice PDF uploads.",
    )
    s3_presigned_url_expires_seconds: int = Field(
        default=3600,
        ge=60,
        description="Presigned S3 GET URL lifetime in seconds.",
    )


def resolved_dotenv_path() -> Path | None:
    """Path to ``.env`` when that file exists and is loaded; else ``None`` (env-only)."""
    return _ENV_FILE


@lru_cache
def get_settings() -> Settings:
    return Settings()
