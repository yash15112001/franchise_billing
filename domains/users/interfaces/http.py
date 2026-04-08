from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from domains.users.application.service import (
    create_user_for_actor,
    get_permissions_for_existing_user,
    get_permissions_for_role,
    get_user_for_actor,
    list_users_for_actor,
    serialize_user_detail,
    serialize_user_summary,
    reset_password_for_actor,
    update_user_active_status_for_actor,
    update_user_access_for_actor,
    update_user_permissions_for_actor,
    update_user_profile_for_actor,
)
from domains.users.domain.access import (
    ACTIVATE_USERS,
    CREATE_USERS,
    DEACTIVATE_USERS,
    MAIN_ADMIN_ROLE,
    RESET_USER_PASSWORD,
    UPDATE_USER_ACCESS,
    UPDATE_USER_PERMISSIONS,
    UPDATE_USER_PROFILE,
    VIEW_USERS,
    VIEW_USER_PERMISSIONS,
    UserRole,
)
from domains.users.interfaces.schemas import (
    CreateUserRequest,
    ResetPasswordRequest,
    UpdateUserAccessRequest,
    UpdateUserPermissionsRequest,
    UpdateUserProfileRequest,
)
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.web.dependencies import UserContext, require_permissions
from foundation.web.responses import error_response, internal_error_response, success_response

router = APIRouter(prefix="/users", tags=["users"])


# TODO : Add pagination in this api
@router.get("")
def list_users(
        search: str | None = Query(default=None),
        full_name: str | None = Query(default=None),
        username: str | None = Query(default=None),
        franchise_id: int | None = Query(default=None),
        email: str | None = Query(default=None),
        role: UserRole | None = Query(default=None),
        context: UserContext = Depends(require_permissions(VIEW_USERS)),
        db: Session = Depends(get_db),
) -> dict:
    """Search/list users visible to the actor (franchise-scoped for non–main-admin).

    **Query:** `search`, `full_name`, `username`, `franchise_id`, `email`, `role`.

    **Auth:** `VIEW_USERS`. **Success:** 200 — `data`: user summary rows. **Errors:** AppError; 422 / 500.
    """
    try:
        users = list_users_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            search=search,
            full_name=full_name,
            username=username,
            franchise_id=franchise_id,
            email=email,
            role=role,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Users fetched successfully.",
            data=[serialize_user_summary(user) for user in users],
            status_code=status.HTTP_200_OK,
        )


@router.post("")
def create_user(
        payload: CreateUserRequest,
        context: UserContext = Depends(require_permissions(CREATE_USERS)),
        db: Session = Depends(get_db),
) -> dict:
    """Create a user (role/franchise per contract).

    **Body:** `CreateUserRequest`. **Auth:** `CREATE_USERS`.

    **Success:** 201 — created user fields. **Errors:** AppError (duplicate username, invalid franchise, …). 422 / 500.
    """
    try:
        user = create_user_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            username=payload.username,
            password=payload.password,
            role=payload.role,
            franchise_id=payload.franchise_id,
            full_name=payload.full_name,
            email=payload.email,
            extra_permissions=payload.extra_permissions,
            revoked_permissions=payload.revoked_permissions,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        return success_response(
            message="User created successfully.",
            data={
                "id": user.id,
                "username": user.username,
                "role": user.role.value,
                "franchise_id": user.franchise_id,
                "full_name": user.full_name,
                "email": user.email,
                "created_at": str(user.created_at),
                "updated_at": str(user.updated_at),
            },
            status_code=status.HTTP_201_CREATED,
        )


@router.get("/permissions")
def get_user_permissions_by_role(
    role: UserRole = Query(...),
    context: UserContext = Depends(require_permissions(VIEW_USER_PERMISSIONS)),
) -> dict:
    """Return permission sets for a **role** (main admin only).

    **Query:** `role` (required). **Auth:** `VIEW_USER_PERMISSIONS`.

    **Success:** 200 — permission discovery payload. **Errors:** `FORBIDDEN_PERMISSION_DISCOVERY` (403) if not main admin. 422 / 500.
    """
    try:
        if context.role.value != MAIN_ADMIN_ROLE:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only main admin can access user permission discovery.",
                error_code="FORBIDDEN_PERMISSION_DISCOVERY",
            )
        data = get_permissions_for_role(role)
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="User permissions fetched successfully.",
            data=data,
            status_code=status.HTTP_200_OK,
        )


# TODO : subtle, yet important bug here
# there is sutble issue in permission module where even if franchise_admin does not have some permission, he can still assign those permission to its emplpoyees
# so to resolve it, when getting the permission config for user, based on who is requesting, we have to make sure that extadable permissions in that reponse does not contain permissions which the requester user does not have
@router.get("/{user_id}/permissions")
def get_existing_user_permissions(
        user_id: int,
        context: UserContext = Depends(
            require_permissions(VIEW_USER_PERMISSIONS)),
        db: Session = Depends(get_db),
) -> dict:
    """Permission config for an **existing** user id (main admin only).

    **Path:** `user_id`. **Auth:** `VIEW_USER_PERMISSIONS`.

    **Success:** 200. **Errors:** `FORBIDDEN_PERMISSION_DISCOVERY`, … 422 / 500.
    """
    try:
        if context.role.value != MAIN_ADMIN_ROLE:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only main admin can access user permission discovery.",
                error_code="FORBIDDEN_PERMISSION_DISCOVERY",
            )
        data = get_permissions_for_existing_user(db, user_id=user_id)
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Existing user permissions fetched successfully.",
            data=data,
            status_code=status.HTTP_200_OK,
        )


@router.get("/{user_id}")
def get_user(
        user_id: int,
        context: UserContext = Depends(require_permissions(VIEW_USERS)),
        db: Session = Depends(get_db),
) -> dict:
    """User detail including franchise summary when applicable.

    **Path:** `user_id`. **Auth:** `VIEW_USERS`.

    **Success:** 200 — `serialize_user_detail`. **Errors:** user not found / forbidden AppError. 422 / 500.
    """
    try:
        user, franchise = get_user_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            user_id=user_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="User fetched successfully.",
            data=serialize_user_detail(user, franchise),
            status_code=status.HTTP_200_OK,
        )


@router.patch("/{user_id}/profile")
def update_user_profile(
        user_id: int,
        payload: UpdateUserProfileRequest,
        context: UserContext = Depends(
            require_permissions(UPDATE_USER_PROFILE)),
        db: Session = Depends(get_db),
) -> dict:
    """Update profile fields (`full_name`, `email`, … per `UpdateUserProfileRequest`).

    **Path:** `user_id`. **Body:** `UpdateUserProfileRequest`. **Auth:** `UPDATE_USER_PROFILE`.

    **Success:** 200 — `user_id`, `updated_at`. **Errors:** AppError. 422 / 500.
    """
    try:
        user = update_user_profile_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            user_id=user_id,
            full_name=payload.full_name,
            email=payload.email,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        return success_response(
            message="User profile updated successfully.",
            data={
                "user_id": user.id,
                "updated_at": str(user.updated_at)
            },
            status_code=status.HTTP_200_OK,
        )


@router.patch("/{user_id}/access")
def update_user_access(
        user_id: int,
        payload: UpdateUserAccessRequest,
        context: UserContext = Depends(
            require_permissions(UPDATE_USER_ACCESS)),
        db: Session = Depends(get_db),
) -> dict:
    """Change franchise assignment and/or role (`UpdateUserAccessRequest`).

    **Path:** `user_id`. **Auth:** `UPDATE_USER_ACCESS`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        user = update_user_access_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            user_id=user_id,
            franchise_id=payload.franchise_id,
            role=payload.role,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        return success_response(
            message="User access updated successfully.",
            data={
                "user_id": user.id,
                "updated_at": str(user.updated_at)
            },
            status_code=status.HTTP_200_OK,
        )


# TODO : detailed in-depth of testing required for permissions management
@router.patch("/{user_id}/permissions")
def update_user_permissions(
        user_id: int,
        payload: UpdateUserPermissionsRequest,
        context: UserContext = Depends(
            require_permissions(UPDATE_USER_PERMISSIONS)),
        db: Session = Depends(get_db),
) -> dict:
    """Apply extra/revoked permission deltas (`UpdateUserPermissionsRequest`).

    **Path:** `user_id`. **Auth:** `UPDATE_USER_PERMISSIONS`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        user = update_user_permissions_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            user_id=user_id,
            extra_permissions_delta=payload.extra_permissions,
            revoked_permissions_delta=payload.revoked_permissions,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        return success_response(
            message="User permissions updated successfully.",
            data={
                "user_id": user.id,
                "updated_at": str(user.updated_at),
            },
            status_code=status.HTTP_200_OK,
        )


@router.patch("/{user_id}/deactivate")
def deactivate_user(
        user_id: int,
        context: UserContext = Depends(require_permissions(DEACTIVATE_USERS)),
        db: Session = Depends(get_db),
) -> dict:
    """Set user `is_active` false. **Auth:** `DEACTIVATE_USERS`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        user = update_user_active_status_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            user_id=user_id,
            is_active=False,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        return success_response(
            message="User deactivated successfully.",
            data={
                "id": user.id,
                "is_active": user.is_active,
                "updated_at": str(user.updated_at),
            },
            status_code=status.HTTP_200_OK,
        )


@router.patch("/{user_id}/activate")
def activate_user(
        user_id: int,
        context: UserContext = Depends(require_permissions(ACTIVATE_USERS)),
        db: Session = Depends(get_db),
) -> dict:
    """Set user `is_active` true. **Auth:** `ACTIVATE_USERS`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        user = update_user_active_status_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            user_id=user_id,
            is_active=True,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        return success_response(
            message="User activated successfully.",
            data={
                "id": user.id,
                "is_active": user.is_active,
                "updated_at": str(user.updated_at),
            },
            status_code=status.HTTP_200_OK,
        )


@router.patch("/{user_id}/reset-password")
def reset_user_password(
        user_id: int,
        payload: ResetPasswordRequest,
        context: UserContext = Depends(
            require_permissions(RESET_USER_PASSWORD)),
        db: Session = Depends(get_db),
) -> dict:
    """Admin reset password (`ResetPasswordRequest` — `new_password`).

    **Path:** `user_id`. **Auth:** `RESET_USER_PASSWORD`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        user = reset_password_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            user_id=user_id,
            new_password=payload.new_password,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        return success_response(
            message="Password reset successfully.",
            data={
                "user_id": user.id,
                "updated_at": str(user.updated_at),
            },
            status_code=status.HTTP_200_OK,
        )
