from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from domains.auth.application.service import (
    authenticate_user,
    bootstrap_main_admin as bootstrap_main_admin_user,
    change_password as change_user_password,
    serialize_authenticated_user,
)
from domains.auth.interfaces.schemas import BootstrapMainAdminRequest, ChangePasswordRequest, LoginRequest
from domains.users.domain.access import MAIN_ADMIN_ROLE
from domains.users.domain.access import VIEW_USERS
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.web.dependencies import UserContext, require_permissions
from foundation.web.responses import error_response, internal_error_response, success_response

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/bootstrap-main-admin")
def bootstrap_main_admin(
        payload: BootstrapMainAdminRequest, db: Session = Depends(get_db)) -> dict:
    """Create the first main-admin user (setup / dev only; requires bootstrap secret).

    **Body:** `BootstrapMainAdminRequest` — `full_name`, `username`, `password`, `email`, `bootstrap_secret`.

    **Success:** 201 — `data`: new user id, username, role, `created_at`.
    **Errors:** AppError (400/403/… per service); `error_code` in body. 422 — validation (`VALIDATION_ERROR`). 500 — `INTERNAL_SERVER_ERROR`.
    """
    try:
        user = bootstrap_main_admin_user(
            db,
            full_name=payload.full_name,
            username=payload.username,
            password=payload.password,
            email=payload.email,
            bootstrap_secret=payload.bootstrap_secret,
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
            message="Main admin bootstrapped successfully.",
            data={
                "id": user.id,
                "username": user.username,
                "role": MAIN_ADMIN_ROLE,
                "created_at": str(user.created_at),
            },
            status_code=status.HTTP_201_CREATED,
        )


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    """Authenticate with username/password; returns JWT and user summary.

    **Body:** `LoginRequest` — `username`, `password`.

    **Success:** 200 — `data`: `access_token`, `token_type`, `user` (id, role, franchise_id, …).
    **Errors:** AppError (401 invalid credentials, etc.); `error_code` in body. 422 — `VALIDATION_ERROR`. 500 — `INTERNAL_SERVER_ERROR`.
    """
    try:
        user, token = authenticate_user(db,
                                        username=payload.username,
                                        password=payload.password)
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Login successful.",
            data={
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role.value,
                    "franchise_id": user.franchise_id,
                    "full_name": user.full_name,
                    "email": user.email,
                },
            },
        )


@router.get("/me")
def get_authenticated_user(
        context: UserContext = Depends(require_permissions(VIEW_USERS)),
) -> dict:
    """Return the current user profile (requires valid Bearer token).

    **Auth:** permission `VIEW_USERS` (see access module).

    **Success:** 200 — `data`: serialized user (see `serialize_authenticated_user`).
    **Errors:** 401 if token invalid; 403 if permission denied. AppError envelope. 500 — `INTERNAL_SERVER_ERROR`.
    """
    return success_response(
        message="Authenticated user fetched successfully.",
        data=serialize_authenticated_user(context.user),
    )


@router.patch("/change-password")
def change_password(
        payload: ChangePasswordRequest,
        db: Session = Depends(get_db),
        context: UserContext = Depends(require_permissions(VIEW_USERS)),
) -> dict:
    """Change password for the authenticated user.

    **Body:** `ChangePasswordRequest` — `old_password`, `new_password`.

    **Success:** 200 — `data`: `user_id`, `updated_at`.
    **Errors:** AppError (e.g. wrong old password); `error_code` in body. 422 — `VALIDATION_ERROR`. 500 — `INTERNAL_SERVER_ERROR`.
    """
    try:
        user = change_user_password(
            db,
            user=context.user,
            old_password=payload.old_password,
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
            message="Password changed successfully.",
            data={
                "user_id": user.id,
                "updated_at": str(user.updated_at)
            },
        )


@router.post("/token", include_in_schema=False)
def login_for_docs(
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: Session = Depends(get_db),
) -> dict:
    """OAuth2 password form for Swagger UI “Authorize” (hidden from schema).

    **Body (form):** `username`, `password`.

    **Success:** 200 — raw `{ "access_token", "token_type" }` (not the usual `success` envelope).
    **Errors:** JSON `detail` message on failure (differs from standard `error_response` envelope).
    """
    try:
        _, token = authenticate_user(db,
                                     username=form_data.username,
                                     password=form_data.password)
    except AppError as exc:
        return JSONResponse(status_code=exc.status_code,
                            content={"detail": exc.message})
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )
    else:
        return {"access_token": token, "token_type": "bearer"}
