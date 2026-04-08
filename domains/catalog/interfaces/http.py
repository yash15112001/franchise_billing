from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from starlette import status

from domains.catalog.application.service import (
    create_service_for_actor,
    get_active_service_by_id,
    list_active_services,
    list_all_services_including_inactive,
    serialize_service_status_toggle_response,
    serialize_service_row,
    set_service_status_for_actor,
)
from domains.catalog.interfaces.schemas import (
    ServiceCreateRequest,
    ServicePatchRequest,
)
from domains.users.domain.access import (
    ACTIVATE_SERVICES,
    CREATE_SERVICES,
    DEACTIVATE_SERVICES,
    VIEW_SERVICES,
)
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.web.dependencies import UserContext, require_permissions
from foundation.web.responses import error_response, internal_error_response, success_response

router = APIRouter(prefix="/services", tags=["services"])


@router.get("")
def list_services(
        search: str | None = Query(default=None),
        name: str | None = Query(default=None),
        vehicle_type: str | None = Query(default=None),
        service_category: str | None = Query(default=None),
        _context: UserContext = Depends(require_permissions(VIEW_SERVICES)),
        db: Session = Depends(get_db),
) -> dict:
    """List **active** catalog services with optional filters.

    **Query:** `search`, `name`, `vehicle_type`, `service_category`. **Auth:** `VIEW_SERVICES`.

    **Success:** 200 — `data`: array of service rows. **Errors:** AppError / 422 / 500.
    """
    try:
        services = list_active_services(
            db,
            search=search,
            name=name,
            vehicle_type=vehicle_type,
            service_category=service_category,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Services fetched successfully.",
            data=[serialize_service_row(s) for s in services],
            status_code=status.HTTP_200_OK,
        )


@router.get("/all")
def list_all_services(
        search: str | None = Query(default=None),
        name: str | None = Query(default=None),
        vehicle_type: str | None = Query(default=None),
        service_category: str | None = Query(default=None),
        context: UserContext = Depends(require_permissions(VIEW_SERVICES)),
        db: Session = Depends(get_db),
) -> dict:
    """List active **and** inactive services (restricted to main admin in service layer).

    **Query:** same as `GET /services`. **Auth:** `VIEW_SERVICES`.

    **Success:** 200 — `data`: rows include `is_active` where applicable. **Errors:** 403 if not main admin (service); 422 / 500.
    """
    try:
        services = list_all_services_including_inactive(
            db,
            actor_role=context.role,
            search=search,
            name=name,
            vehicle_type=vehicle_type,
            service_category=service_category,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Services fetched successfully.",
            data=[
                serialize_service_row(s, include_is_active=True)
                for s in services
            ],
            status_code=status.HTTP_200_OK,
        )


@router.post("")
def create_service(
        payload: ServiceCreateRequest,
        context: UserContext = Depends(require_permissions(CREATE_SERVICES)),
        db: Session = Depends(get_db),
) -> dict:
    """Create a catalog service.

    **Body:** `ServiceCreateRequest`. **Auth:** `CREATE_SERVICES`.

    **Success:** 201 — `data`: created service row. **Errors:** AppError; 422 / 500.
    """
    try:
        service = create_service_for_actor(
            db,
            name=payload.name,
            vehicle_type=payload.vehicle_type,
            service_category=payload.service_category,
            discount_percentage=payload.discount_percentage,
            estimated_duration=payload.estimated_duration,
            base_price=payload.base_price,
            description=payload.description,
            actor_user_id=context.user.id,
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
            message="Service created successfully.",
            data=serialize_service_row(service),
            status_code=status.HTTP_201_CREATED,
        )


@router.get("/{service_id}")
def get_service(
        service_id: int,
        _context: UserContext = Depends(require_permissions(VIEW_SERVICES)),
        db: Session = Depends(get_db),
) -> dict:
    """Get one **active** service by id.

    **Path:** `service_id`. **Auth:** `VIEW_SERVICES`.

    **Success:** 200 — `data`: service row. **Errors:** not found (AppError); 422 / 500.
    """
    try:
        service = get_active_service_by_id(db, service_id=service_id)
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Service fetched successfully.",
            data=serialize_service_row(service),
            status_code=status.HTTP_200_OK,
        )


# TODO : implement patch on service as deactive old nd create new service.
@router.patch("/{service_id}", include_in_schema=False)
def patch_service(
        _service_id: int,
        _payload: ServicePatchRequest,
        _context: UserContext = Depends(require_permissions(CREATE_SERVICES)),
        _db: Session = Depends(get_db),
) -> dict:
    """Not implemented — use deactivate + create. Returns 501 `NOT_IMPLEMENTED`. Hidden from OpenAPI."""
    raise AppError(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        message="This endpoint is not implemented yet.",
        error_code="NOT_IMPLEMENTED",
    )


@router.patch("/{service_id}/deactivate")
def deactivate_service(
        service_id: int,
        context: UserContext = Depends(
            require_permissions(DEACTIVATE_SERVICES)),
        db: Session = Depends(get_db),
) -> dict:
    """Soft-deactivate a service (`is_active` false).

    **Path:** `service_id`. **Auth:** `DEACTIVATE_SERVICES`.

    **Success:** 200 — toggle response payload. **Errors:** AppError; 422 / 500.
    """
    try:
        service = set_service_status_for_actor(
            db,
            service_id=service_id,
            is_active=False,
            actor_role=context.role,
            actor_user_id=context.user.id,
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
            message="Service deactivated successfully.",
            data=serialize_service_status_toggle_response(service),
            status_code=status.HTTP_200_OK,
        )


@router.patch("/{service_id}/activate")
def activate_service(
        service_id: int,
        context: UserContext = Depends(require_permissions(ACTIVATE_SERVICES)),
        db: Session = Depends(get_db),
) -> dict:
    """Re-activate a service.

    **Path:** `service_id`. **Auth:** `ACTIVATE_SERVICES`.

    **Success:** 200 — toggle response payload. **Errors:** AppError; 422 / 500.
    """
    try:
        service = set_service_status_for_actor(
            db,
            service_id=service_id,
            is_active=True,
            actor_role=context.role,
            actor_user_id=context.user.id,
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
            message="Service activated successfully.",
            data=serialize_service_status_toggle_response(service),
            status_code=status.HTTP_200_OK,
        )
