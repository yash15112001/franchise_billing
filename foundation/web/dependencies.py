from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.franchises.domain.enums import FranchiseStatus
from domains.franchises.infrastructure.models import Franchise
from domains.users.domain.access import UserRole, resolve_effective_permissions
from domains.users.infrastructure.models import User
from foundation.config.settings import get_settings
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.security.auth import decode_access_token
from foundation.web.context import FranchiseScope, UserContext

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_prefix}/auth/token")


def _get_user_context(
    *,
    token: str,
    db: Session,
    x_franchise_id: int | None = None,
) -> UserContext:
    try:
        payload = decode_access_token(token)
        user_id = payload["user_id"]
    except Exception as exc:  # pragma: no cover - auth decoding failures map to 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
        ) from exc

    # Only active users may authenticate; deactivated users are indistinguishable
    # from unknown ids here (same 401) unless we split the query for messaging.
    user = db.scalar(
        select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User not found.")

    permissions = resolve_effective_permissions(
        user.role,
        user.extra_permissions,
        user.revoked_permissions,
    )
    active_franchise_id = user.franchise_id or x_franchise_id
    if user.role is not UserRole.MAIN_ADMIN:
        if user.franchise_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not assigned to a franchise.",
            )
        # TODO : this must be included as part of resolution
        # also, have to think if its allowed in some api cases.

        # franchise = db.get(Franchise, user.franchise_id)
        # if franchise is None:
        #     raise AppError(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         message="User's franchise could not be loaded.",
        #         error_code="FRANCHISE_MISSING_FOR_USER",
        #         details={"franchise_id": user.franchise_id},
        #     )
        # if franchise.status is not FranchiseStatus.ACTIVE:
        #     raise AppError(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         message=
        #         ("Operations are not allowed while your franchise is not active."
        #          ),
        #         error_code="FRANCHISE_NOT_ACTIVE",
        #         details={"franchise_status": franchise.status.value},
        #     )
        if x_franchise_id is not None and x_franchise_id != user.franchise_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to the requested franchise.",
            )
        active_franchise_id = user.franchise_id

    return UserContext(
        user=user,
        active_franchise_id=active_franchise_id,
        permissions=permissions,
        role=user.role,
    )


def get_current_user_context(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db),
) -> UserContext:
    return _get_user_context(token=token, db=db)


def get_franchise_scope(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    x_franchise_id: int | None = Header(default=None, alias="X-Franchise-Id"),
) -> FranchiseScope:
    context = _get_user_context(token=token,
                                db=db,
                                x_franchise_id=x_franchise_id)
    if context.franchise_id is None:
        raise HTTPException(
            status_code=400,
            detail=
            "X-Franchise-Id header is required for main admin franchise-scoped requests.",
        )

    franchise = db.scalar(
        select(Franchise).where(Franchise.id == context.franchise_id))
    if franchise is None:
        raise HTTPException(status_code=404, detail="Franchise not found.")

    return FranchiseScope(franchise_id=franchise.id)


def require_permissions(*required_permissions: str):

    def dependency(context: UserContext = Depends(
        get_current_user_context)) -> UserContext:
        missing_permissions = [
            item for item in required_permissions
            if item not in context.permissions
        ]
        if missing_permissions:
            joined = ", ".join(missing_permissions)
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message=f"Missing permissions: {joined}",
                error_code="FORBIDDEN_MISSING_PERMISSIONS",
                details={"missing_permissions": list(missing_permissions)},
            )
        return context

    return dependency
