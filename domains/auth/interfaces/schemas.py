from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

from domains.users.domain.utils import (
    normalize_full_name,
    normalize_optional_email,
    normalize_username,
)


class BootstrapMainAdminRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8)
    email: EmailStr | None = None
    bootstrap_secret: str

    @field_validator("username")
    @classmethod
    def username_trim_preserve_case(cls, v: str) -> str:
        return normalize_username(v)

    @field_validator("full_name")
    @classmethod
    def full_name_trim_preserve_case(cls, v: str) -> str:
        return normalize_full_name(v)

    @field_validator("email", mode="before")
    @classmethod
    def email_trim_preserve_case(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return normalize_optional_email(v)
        return v


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str

    @field_validator("username")
    @classmethod
    def username_trim_preserve_case(cls, v: str) -> str:
        return normalize_username(v)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)
