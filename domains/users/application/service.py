from __future__ import annotations

import logging

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from domains.audit.application.service import write_audit_log
from domains.franchises.infrastructure.models import Franchise
from foundation.errors import AppError
from foundation.security.auth import (
    hash_password,
    validate_password_strength,
    verify_password,
)

from domains.users.domain.access import (
    DEFAULT_ROLE_PERMISSIONS,
    VALID_PERMISSION_CODES,
    UserRole,
)
from domains.users.infrastructure.models import User

logger = logging.getLogger(__name__)


def serialize_user_summary(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role.value,
        "franchise_id": user.franchise_id,
        "full_name": user.full_name,
        "email": user.email,
    }


def serialize_franchise_detail(franchise: Franchise | None) -> dict | None:
    if franchise is None:
        return None

    return {
        "id": franchise.id,
        "name": franchise.name,
        "code": franchise.code,
        "city": franchise.city,
        "state": franchise.state,
        "created_at": str(franchise.created_at),
    }


def serialize_user_detail(user: User, franchise: Franchise | None) -> dict:
    data = serialize_user_summary(user)
    data["franchise"] = serialize_franchise_detail(franchise)
    return data


def list_users_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    search: str | None,
    full_name: str | None,
    username: str | None,
    franchise_id: int | None,
    email: str | None,
    role: UserRole | None,
) -> list[User]:
    statement = select(User)

    if actor_role is UserRole.MAIN_ADMIN:
        pass
    elif actor_role is UserRole.FRANCHISE_ADMIN:
        statement = statement.where(User.franchise_id == actor_franchise_id)
    else:
        statement = statement.where(User.id == actor.id)

    if search:
        statement = statement.where(
            or_(
                User.username.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
            ))
    if full_name:
        statement = statement.where(User.full_name.ilike(f"%{full_name}%"))
    if username:
        statement = statement.where(User.username.ilike(f"%{username}%"))
    if franchise_id is not None:
        statement = statement.where(User.franchise_id == franchise_id)
    if email:
        statement = statement.where(User.email.ilike(f"%{email}%"))
    if role is not None:
        statement = statement.where(User.role == role)

    statement = statement.order_by(User.full_name.asc(), User.id.asc())
    return list(db.scalars(statement).all())


def get_user_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    user_id: int,
) -> tuple[User, Franchise | None]:
    statement = (select(User, Franchise).outerjoin(
        Franchise,
        Franchise.id == User.franchise_id).where(User.id == user_id))

    if actor_role is UserRole.MAIN_ADMIN:
        pass
    elif actor_role is UserRole.FRANCHISE_ADMIN:
        statement = statement.where(User.franchise_id == actor_franchise_id)
    else:
        statement = statement.where(User.id == actor.id)

    row = db.execute(statement).first()
    if row is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found.",
            error_code="USER_NOT_FOUND",
            details={"user_id": user_id},
        )

    user, franchise = row
    return user, franchise


def create_user_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    username: str,
    password: str,
    role: UserRole,
    franchise_id: int | None,
    full_name: str,
    email: str | None,
    extra_permissions: list[str],
    revoked_permissions: list[str],
) -> User:
    """Create a user. Fields are expected to match ``CreateUserRequest`` (validated there)."""

    if role is UserRole.MAIN_ADMIN:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Main admin must be created only through bootstrap.",
            error_code="INVALID_USER_ROLE",
        )

    resolved_franchise_id = franchise_id
    if actor_role is UserRole.FRANCHISE_ADMIN:
        if role not in {
                UserRole.FRANCHISE_ADMIN, UserRole.FRANCHISE_STAFF_MEMBER
        }:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message=
                "Franchise admin can create only franchise admin or franchise staff users.",
                error_code="FORBIDDEN_ROLE_ASSIGNMENT",
            )
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise admin must belong to a franchise.",
                error_code="MISSING_ACTOR_FRANCHISE",
            )
        if franchise_id is not None and franchise_id != actor_franchise_id:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message=
                ("Franchise admin can create users only in their own franchise."
                 ),
                error_code="FORBIDDEN_FOREIGN_FRANCHISE",
                details={
                    "requested_franchise_id": franchise_id,
                    "actor_franchise_id": actor_franchise_id,
                },
            )
        resolved_franchise_id = actor_franchise_id
        if extra_permissions or revoked_permissions:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise admin cannot assign permission overrides.",
                error_code="FORBIDDEN_PERMISSION_OVERRIDE",
            )
    elif actor_role is UserRole.MAIN_ADMIN and resolved_franchise_id is None:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Franchise id is required when main admin creates a user.",
            error_code="MISSING_FRANCHISE_ID",
        )

    invalid_extra_permissions = sorted({
        permission
        for permission in extra_permissions
        if permission not in VALID_PERMISSION_CODES
    })
    if invalid_extra_permissions:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="One or more extra permissions are invalid.",
            error_code="INVALID_EXTRA_PERMISSIONS",
            details={"permissions": invalid_extra_permissions},
        )

    invalid_revoked_permissions = sorted({
        permission
        for permission in revoked_permissions
        if permission not in VALID_PERMISSION_CODES
    })
    if invalid_revoked_permissions:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="One or more revoked permissions are invalid.",
            error_code="INVALID_REVOKED_PERMISSIONS",
            details={"permissions": invalid_revoked_permissions},
        )

    overlap = sorted(set(extra_permissions) & set(revoked_permissions))
    if overlap:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="The same permission cannot be both granted and revoked.",
            error_code="OVERLAPPING_PERMISSION_OVERRIDES",
            details={"permissions": overlap},
        )

    # TODO : checking weather the franchise exists from resolved_franchise_id is pointless
    # since due to fKey constraints the db handles it be default
    if resolved_franchise_id is None or db.scalar(
            select(Franchise.id).where(
                Franchise.id == resolved_franchise_id)) is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Franchise not found.",
            error_code="FRANCHISE_NOT_FOUND",
            details={"franchise_id": resolved_franchise_id},
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
        role=role,
        franchise_id=resolved_franchise_id,
        is_active=True,
        full_name=full_name,
        email=email,
        extra_permissions=list(dict.fromkeys(extra_permissions)),
        revoked_permissions=list(dict.fromkeys(revoked_permissions)),
    )
    db.add(user)

    try:
        db.flush()
    except IntegrityError as exc:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message=
            "A user with the same username already exists in this franchise.",
            error_code="DUPLICATE_USERNAME_IN_FRANCHISE",
            details={
                "username": username,
                "franchise_id": resolved_franchise_id
            },
        ) from exc

    write_audit_log(
        db,
        action="user.create",
        entity_name="users",
        entity_id=str(user.id),
        actor_user_id=actor.id,
        franchise_id=resolved_franchise_id,
        payload={
            "username": username,
            "role": role.value
        },
    )

    return user


def update_user_profile_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    user_id: int,
    full_name: str | None,
    email: str | None,
) -> User:
    """Update profile. ``full_name`` / ``email`` are expected to match ``UpdateUserProfileRequest`` when set."""

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found.",
            error_code="USER_NOT_FOUND",
            details={"user_id": user_id},
        )

    if actor.id == user.id:
        pass
    elif actor_role is UserRole.MAIN_ADMIN:
        pass
    elif actor_role is UserRole.FRANCHISE_ADMIN:
        if actor_franchise_id is None or user.franchise_id != actor_franchise_id:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message=
                "Franchise admin can update profile only for users in the same franchise.",
                error_code="FORBIDDEN_PROFILE_UPDATE_SCOPE",
                details={"user_id": user_id},
            )
    else:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="You can update only your own profile.",
            error_code="FORBIDDEN_PROFILE_UPDATE_SCOPE",
            details={"user_id": user_id},
        )

    if full_name is not None:
        user.full_name = full_name
    if email is not None:
        user.email = email

    db.add(user)
    db.flush()

    write_audit_log(
        db,
        action="user.update_profile",
        entity_name="users",
        entity_id=str(user.id),
        actor_user_id=actor.id,
        franchise_id=user.franchise_id,
        payload={
            "full_name": full_name,
            "email": email
        },
    )
    return user


def update_user_access_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    user_id: int,
    franchise_id: int | None,
    role: UserRole | None,
) -> User:
    if actor_role is not UserRole.MAIN_ADMIN:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only main admin can update user access.",
            error_code="FORBIDDEN_ACCESS_UPDATE",
        )

    if franchise_id is None and role is None:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="At least one access field must be provided.",
            error_code="EMPTY_ACCESS_UPDATE",
        )

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found.",
            error_code="USER_NOT_FOUND",
            details={"user_id": user_id},
        )

    if user.role is UserRole.MAIN_ADMIN:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message=
            "Main admin access cannot be changed through this endpoint.",
            error_code="FORBIDDEN_MAIN_ADMIN_ACCESS_UPDATE",
        )

    if role is UserRole.MAIN_ADMIN:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Main admin must be created only through bootstrap.",
            error_code="INVALID_USER_ROLE",
        )

    resolved_role = role or user.role
    resolved_franchise_id = franchise_id if franchise_id is not None else user.franchise_id

    if resolved_franchise_id is None:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Franchise id is required for franchise users.",
            error_code="MISSING_FRANCHISE_ID",
        )

    if db.scalar(
            select(Franchise.id).where(
                Franchise.id == resolved_franchise_id)) is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Franchise not found.",
            error_code="FRANCHISE_NOT_FOUND",
            details={"franchise_id": resolved_franchise_id},
        )

    user.role = resolved_role
    user.franchise_id = resolved_franchise_id
    db.add(user)
    db.flush()

    write_audit_log(
        db,
        action="user.update_access",
        entity_name="users",
        entity_id=str(user.id),
        actor_user_id=actor.id,
        franchise_id=resolved_franchise_id,
        payload={
            "role": resolved_role.value,
            "franchise_id": resolved_franchise_id,
        },
    )
    return user


def get_permissions_for_role(role: UserRole) -> dict:
    if role not in {UserRole.FRANCHISE_ADMIN, UserRole.FRANCHISE_STAFF_MEMBER}:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=
            "Permissions can only be queried for franchise admin or franchise staff member.",
            error_code="INVALID_ROLE_FOR_PERMISSION_DISCOVERY",
            details={"role": role.value},
        )

    default_permissions = sorted(DEFAULT_ROLE_PERMISSIONS.get(role, set()))
    all_permissions = set(VALID_PERMISSION_CODES)
    extra_permissions_available = sorted(all_permissions -
                                         set(default_permissions))

    return {
        "role": role.value,
        "default_permissions": default_permissions,
        "extra_permissions_available": extra_permissions_available,
        "revokable_permissions": default_permissions,
    }


def get_permissions_for_existing_user(
    db: Session,
    *,
    user_id: int,
) -> dict:
    user = db.scalar(
        select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found.",
            error_code="USER_NOT_FOUND",
            details={"user_id": user_id},
        )

    default_permissions = sorted(DEFAULT_ROLE_PERMISSIONS.get(
        user.role, set()))
    extra_permissions = sorted(set(user.extra_permissions))
    revoked_permissions = sorted(set(user.revoked_permissions))
    effective_permissions = sorted(
        (set(DEFAULT_ROLE_PERMISSIONS.get(user.role, set()))
         | set(extra_permissions)) - set(revoked_permissions))
    extra_permissions_available = sorted(
        set(VALID_PERMISSION_CODES) - set(effective_permissions))

    return {
        "user_id": user.id,
        "role": user.role.value,
        "default_permissions": default_permissions,
        "extra_permissions": extra_permissions,
        "revoked_permissions": revoked_permissions,
        "effective_permissions": effective_permissions,
        "extra_permissions_available": extra_permissions_available,
        "revokable_permissions": default_permissions,
        "removable_extra_permissions": extra_permissions,
    }


def update_user_permissions_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    user_id: int,
    extra_permissions_delta: list[str],
    revoked_permissions_delta: list[str],
) -> User:
    """Apply permission deltas against the current stored lists (not full replacement).

    *extra_permissions_delta*: grant or restore — un-revoke a default permission, or add a
    non-default permission to *extra_permissions*.

    *revoked_permissions_delta*: take away — revoke a default permission, or remove a
    non-default permission from *extra_permissions*.
    """
    if actor_role is not UserRole.MAIN_ADMIN:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only main admin can update user permission overrides.",
            error_code="FORBIDDEN_PERMISSION_UPDATE",
        )

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found.",
            error_code="USER_NOT_FOUND",
            details={"user_id": user_id},
        )

    if user.role is UserRole.MAIN_ADMIN:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message=
            "Main admin permission overrides cannot be changed through this endpoint.",
            error_code="FORBIDDEN_MAIN_ADMIN_PERMISSION_UPDATE",
        )

    print(extra_permissions_delta)
    print(revoked_permissions_delta)
    extra_add = set(extra_permissions_delta)
    revoke_apply = set(revoked_permissions_delta)

    overlap = sorted(extra_add & revoke_apply)
    if overlap:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=
            "The same permission cannot appear in both delta lists in one request.",
            error_code="PERMISSION_DELTA_OVERLAP",
            details={"permissions": overlap},
        )

    invalid_codes = sorted((extra_add | revoke_apply) - VALID_PERMISSION_CODES)
    if invalid_codes:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="One or more permission codes are not valid.",
            error_code="INVALID_PERMISSION_CODES",
            details={"permissions": invalid_codes},
        )

    defaults = set(DEFAULT_ROLE_PERMISSIONS.get(user.role, set()))
    extra_db = set(user.extra_permissions)
    revoked_db = set(user.revoked_permissions)

    for p in extra_add:
        if p in revoked_db:
            revoked_db.discard(p)
        elif p not in defaults:
            extra_db.add(p)

    for p in revoke_apply:
        if p in extra_db:
            extra_db.discard(p)
        elif p in defaults:
            revoked_db.add(p)
        else:
            logger.warning(
                "Ignoring revoke delta for permission the user does not hold "
                "(not in role defaults or extra_permissions): user_id=%s role=%s permission=%s",
                user.id,
                user.role.value,
                p,
            )

    print(extra_db)
    print(revoked_db)
    user.extra_permissions = sorted(extra_db)
    user.revoked_permissions = sorted(revoked_db)
    db.add(user)
    db.flush()

    write_audit_log(
        db,
        action="user.update_permissions",
        entity_name="users",
        entity_id=str(user.id),
        actor_user_id=actor.id,
        franchise_id=user.franchise_id,
        payload={
            "extra_permissions_delta": sorted(extra_add),
            "revoked_permissions_delta": sorted(revoke_apply),
            "extra_permissions": user.extra_permissions,
            "revoked_permissions": user.revoked_permissions,
        },
    )
    return user


def update_user_active_status_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    user_id: int,
    is_active: bool,
) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found.",
            error_code="USER_NOT_FOUND",
            details={"user_id": user_id},
        )

    if user.role is UserRole.MAIN_ADMIN:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message=
            "Main admin active status cannot be changed through this endpoint.",
            error_code="FORBIDDEN_MAIN_ADMIN_STATUS_UPDATE",
        )

    if actor_role is UserRole.MAIN_ADMIN:
        pass
    elif actor_role is UserRole.FRANCHISE_ADMIN:
        if user.role is not UserRole.FRANCHISE_STAFF_MEMBER:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message=
                "Franchise admin can change active status only for franchise staff members.",
                error_code="FORBIDDEN_STATUS_UPDATE_ROLE",
                details={"user_id": user_id},
            )
        if actor_franchise_id is None or user.franchise_id != actor_franchise_id:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message=
                "Franchise admin can change active status only within the same franchise.",
                error_code="FORBIDDEN_STATUS_UPDATE_SCOPE",
                details={"user_id": user_id},
            )
    else:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="You are not allowed to change active status of any user.",
            error_code="FORBIDDEN_STATUS_UPDATE",
            details={"user_id": user_id},
        )

    if user.is_active != is_active:
        user.is_active = is_active
        db.add(user)
        db.flush()

    write_audit_log(
        db,
        action="user.activate" if is_active else "user.deactivate",
        entity_name="users",
        entity_id=str(user.id),
        actor_user_id=actor.id,
        franchise_id=user.franchise_id,
        payload={"is_active": is_active},
    )
    return user


def reset_password_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    user_id: int,
    new_password: str,
) -> User:
    if actor.id == user_id:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=
            "Use the change-password endpoint to update your own password.",
            error_code="FORBIDDEN_SELF_PASSWORD_RESET",
        )

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found.",
            error_code="USER_NOT_FOUND",
            details={"user_id": user_id},
        )

    # have to think on this:
    if user.role is UserRole.MAIN_ADMIN:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message=
            "Main admin password cannot be reset through this endpoint.",
            error_code="FORBIDDEN_MAIN_ADMIN_PASSWORD_RESET",
        )

    if actor_role is UserRole.MAIN_ADMIN:
        pass
    elif actor_role is UserRole.FRANCHISE_ADMIN:
        if user.role is not UserRole.FRANCHISE_STAFF_MEMBER:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message=
                "Franchise admin can reset password only for franchise staff members.",
                error_code="FORBIDDEN_PASSWORD_RESET_ROLE",
                details={"user_id": user_id},
            )
        if actor_franchise_id is None or user.franchise_id != actor_franchise_id:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message=
                "Franchise admin can reset password only within the same franchise.",
                error_code="FORBIDDEN_PASSWORD_RESET_SCOPE",
                details={"user_id": user_id},
            )
    else:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="You are not allowed to reset any user's password.",
            error_code="FORBIDDEN_PASSWORD_RESET",
            details={"user_id": user_id},
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
    db.flush()

    write_audit_log(
        db,
        action="user.reset_password",
        entity_name="users",
        entity_id=str(user.id),
        actor_user_id=actor.id,
        franchise_id=user.franchise_id,
        payload={},
    )
    return user
