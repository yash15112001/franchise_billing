from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

from domains.users.domain.access import UserRole
from domains.users.domain.utils import (
    normalize_full_name,
    normalize_optional_email,
    normalize_username,
)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8)
    role: UserRole
    franchise_id: int | None = None
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    extra_permissions: list[str] = Field(default_factory=list)
    revoked_permissions: list[str] = Field(default_factory=list)

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


class UpdateUserProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None

    @field_validator("full_name")
    @classmethod
    def full_name_trim_preserve_case(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_full_name(v)

    @field_validator("email", mode="before")
    @classmethod
    def email_trim_preserve_case(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return normalize_optional_email(v)
        return v


class UpdateUserAccessRequest(BaseModel):
    franchise_id: int | None = None
    role: UserRole | None = None


class UpdateUserPermissionsRequest(BaseModel):
    extra_permissions: list[str] = Field(
        default_factory=list,
        description=
        ("Delta: grant or restore (un-revoke) a default permission, or add a non-default "
         "permission to extra_permissions."),
    )
    revoked_permissions: list[str] = Field(
        default_factory=list,
        description=
        ("Delta: take away — revoke a default permission, or remove a non-default "
         "permission from extra_permissions."),
    )


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)
