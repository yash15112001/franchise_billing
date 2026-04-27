from __future__ import annotations

import hmac

from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.audit.application.service import write_audit_log
from domains.users.domain.access import MAIN_ADMIN_ROLE, RESET_USER_PASSWORD, UserRole
from domains.users.domain.utils import (
    normalize_full_name,
    normalize_optional_email,
    normalize_username,
)
from domains.users.infrastructure.models import User
from foundation.config.settings import get_settings
from foundation.errors import AppError
from foundation.security.auth import (
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from fastapi import status


def bootstrap_main_admin(
    db: Session,
    *,
    full_name: str,
    username: str,
    password: str,
    email: str | None,
    bootstrap_secret: str,
) -> User:
    settings = get_settings()
    if not hmac.compare_digest(bootstrap_secret,
                               settings.bootstrap_admin_secret):
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Invalid bootstrap secret.",
            error_code="INVALID_BOOTSTRAP_SECRET",
        )

    if db.scalar(select(User.id).limit(1)) is not None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message="Bootstrap is only allowed before any user is created.",
            error_code="BOOTSTRAP_ALREADY_COMPLETED",
        )

    username = normalize_username(username)
    full_name = normalize_full_name(full_name)
    email = normalize_optional_email(email)

    existing_user = db.scalar(
        select(User).where(User.username == username, User.is_deleted.is_(False)))
    if existing_user is not None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message="Username already exists.",
            error_code="USERNAME_ALREADY_EXISTS",
            details={"username": username},
        )

    password_errors = validate_password_strength(password)
    if password_errors:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Password does not meet the password policy.",
            error_code="WEAK_PASSWORD",
            details={"reasons": password_errors},
        )

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=UserRole.MAIN_ADMIN,
        franchise_id=None,
        is_active=True,
        full_name=full_name,
        email=email,
        extra_permissions=[],
        revoked_permissions=[],
    )
    db.add(user)
    db.flush()

    write_audit_log(
        db,
        action="user.bootstrap_main_admin",
        entity_name="users",
        entity_id=str(user.id),
        actor_user_id=user.id,
        franchise_id=None,
        payload={
            "username": user.username,
            "role": MAIN_ADMIN_ROLE
        },
    )
    return user


def authenticate_user(db: Session, *, username: str,
                      password: str) -> tuple[User, str]:
    try:
        username = normalize_username(username)
    except ValueError as exc:
        raise AppError(
            status_code=401,
            message="Invalid credentials.",
            error_code="INVALID_CREDENTIALS",
        ) from exc

    user = db.scalar(
        select(User).where(User.username == username,
                           User.is_active.is_(True),
                           User.is_deleted.is_(False)))
    if user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found.",
            error_code="USER_NOT_FOUND",
        )

    if not verify_password(password, user.password_hash):
        raise AppError(
            status_code=401,
            message="Invalid credentials.",
            error_code="INVALID_CREDENTIALS",
        )

    token = create_access_token(
        user.id,
        role=user.role.value,
        franchise_id=user.franchise_id,
    )
    return user, token


def change_password(
    db: Session,
    *,
    user: User,
    old_password: str,
    new_password: str,
) -> User:
    if not verify_password(old_password, user.password_hash):
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="Current password is incorrect.",
            error_code="INVALID_OLD_PASSWORD",
        )

    if verify_password(new_password, user.password_hash):
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="New password must be different from the current password.",
            error_code="PASSWORD_REUSE_NOT_ALLOWED",
        )

    password_errors = validate_password_strength(new_password)
    if password_errors:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="New password does not meet the password policy.",
            error_code="WEAK_PASSWORD",
            details={"reasons": password_errors},
        )

    user.password_hash = hash_password(new_password)
    db.add(user)

    write_audit_log(
        db,
        action="user.change_password",
        entity_name="users",
        entity_id=str(user.id),
        actor_user_id=user.id,
        franchise_id=user.franchise_id,
        payload={"permission": RESET_USER_PASSWORD},
    )
    return user


def serialize_authenticated_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role.value,
        "franchise_id": user.franchise_id,
        "full_name": user.full_name,
        "email": user.email,
        "extra_permissions": user.extra_permissions,
        "revoked_permissions": user.revoked_permissions,
        "is_active": user.is_active,
    }
