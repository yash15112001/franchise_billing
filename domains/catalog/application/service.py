from __future__ import annotations

from datetime import time
from decimal import ROUND_HALF_UP, Decimal

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domains.audit.application.service import write_audit_log
from domains.catalog.infrastructure.models import Service
from domains.users.domain.access import UserRole
from foundation.errors import AppError

_TWO = Decimal("0.01")

_ACTIVE_SERVICE_UNIQUE_UQ = "uq_services_active_name_vehicle_category"


def _money(value: Decimal) -> Decimal:
    return value.quantize(_TWO, rounding=ROUND_HALF_UP)


def serialize_service_row(
    service: Service | None,
    *,
    include_is_active: bool = False,
) -> dict:
    """JSON-serializable body matching the service API contract.

    When ``service`` is ``None``, returns ``{}`` (e.g. missing active service by id).
    """
    if service is None:
        return {}
    row = {
        "id": service.id,
        "name": service.name,
        "vehicle_type": service.vehicle_type,
        "service_category": service.service_category,
        "base_price": str(service.base_price),
        "discount_percentage": str(service.discount_percentage),
        "estimated_duration": service.estimated_duration.isoformat(),
        "description": service.description,
        "created_at": str(service.created_at),
        "updated_at": str(service.updated_at),
    }
    if include_is_active:
        row["is_active"] = service.is_active
    return row


def _optional_query_text(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    return s if s else None


def query_services(
    db: Session,
    *,
    service_id: int | None = None,
    is_active: bool | None = True,
    search: str | None = None,
    name: str | None = None,
    vehicle_type: str | None = None,
    service_category: str | None = None,
) -> list[Service]:
    """Query services with optional id filter, active filter, and ``ilike`` / search filters.

    ``is_active``: ``True`` = active only (default), ``False`` = inactive only,
    ``None`` = both (e.g. admin list-all).
    """
    search = _optional_query_text(search)
    name = _optional_query_text(name)
    vehicle_type = _optional_query_text(vehicle_type)
    service_category = _optional_query_text(service_category)

    statement = select(Service).order_by(Service.id.asc())
    if service_id is not None:
        statement = statement.where(Service.id == service_id)
    if is_active is True:
        statement = statement.where(Service.is_active.is_(True))
    elif is_active is False:
        statement = statement.where(Service.is_active.is_(False))

    if name:
        statement = statement.where(Service.name.ilike(f"%{name}%"))
    if vehicle_type:
        statement = statement.where(
            Service.vehicle_type.ilike(f"%{vehicle_type}%"))
    if service_category:
        statement = statement.where(
            Service.service_category.ilike(f"%{service_category}%"), )
    if search:
        q = f"%{search}%"
        statement = statement.where(
            or_(
                Service.name.ilike(q),
                Service.vehicle_type.ilike(q),
                Service.service_category.ilike(q),
                Service.description.ilike(q),
            ), )
    return list(db.scalars(statement).all())


def list_active_services(
    db: Session,
    *,
    search: str | None = None,
    name: str | None = None,
    vehicle_type: str | None = None,
    service_category: str | None = None,
) -> list[Service]:
    """Active services only; see :func:`query_services`."""
    return query_services(
        db,
        is_active=True,
        search=search,
        name=name,
        vehicle_type=vehicle_type,
        service_category=service_category,
    )


def list_all_services_including_inactive(
    db: Session,
    *,
    actor_role: UserRole,
    search: str | None = None,
    name: str | None = None,
    vehicle_type: str | None = None,
    service_category: str | None = None,
) -> list[Service]:
    """Active and inactive; main_admin only. See :func:`query_services`."""
    if actor_role is not UserRole.MAIN_ADMIN:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only main admin can list all services including inactive.",
            error_code="FORBIDDEN_SERVICE_LIST_ALL",
        )
    return query_services(
        db,
        is_active=None,
        search=search,
        name=name,
        vehicle_type=vehicle_type,
        service_category=service_category,
    )


def get_service_by_id(db: Session, *, service_id: int) -> Service | None:
    """Return a service by id regardless of active flag, or ``None``."""
    return db.scalar(select(Service).where(Service.id == service_id))


def get_active_service_by_id(db: Session, *,
                             service_id: int) -> Service | None:
    """Return an **active** service by id, or ``None`` if missing or inactive."""
    rows = query_services(db, service_id=service_id, is_active=True)
    return rows[0] if rows else None


def list_services_by_popularity(
    db: Session,
    *,
    actor_franchise_id: int | None,
    actor_role: str,
) -> list[dict]:
    raise NotImplementedError


def get_service_analytics(
    db: Session,
    *,
    actor_franchise_id: int | None,
    actor_role: str,
) -> dict:
    raise NotImplementedError


def create_service_for_actor(
    db: Session,
    *,
    name: str,
    vehicle_type: str,
    service_category: str,
    discount_percentage: Decimal,
    estimated_duration: time,
    base_price: Decimal,
    description: str | None,
    actor_user_id: int,
) -> Service:
    """Persist a service. Text fields are expected to match ``ServiceCreateRequest`` (normalized there)."""

    item = Service(
        name=name,
        vehicle_type=vehicle_type,
        service_category=service_category,
        base_price=_money(base_price),
        discount_percentage=_money(discount_percentage),
        estimated_duration=estimated_duration,
        description=description,
        is_active=True,
    )
    db.add(item)

    try:
        db.flush()
    except IntegrityError as exc:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message=("An active service with the same name, vehicle type, "
                     "and service category already exists."),
            error_code="DUPLICATE_ACTIVE_SERVICE",
            details={
                "name": name,
                "vehicle_type": vehicle_type,
                "service_category": service_category,
            },
        ) from exc

    write_audit_log(
        db,
        action="catalog.service.create",
        entity_name="services",
        entity_id=str(item.id),
        actor_user_id=actor_user_id,
        franchise_id=None,
        payload={
            "name": item.name,
            "vehicle_type": item.vehicle_type,
            "service_category": item.service_category,
            "base_price": str(item.base_price),
            "discount_percentage": str(item.discount_percentage),
            "estimated_duration": item.estimated_duration.isoformat(),
            "description": item.description,
            "is_active": item.is_active,
        },
    )
    return item


def patch_service(
    _db: Session,
    *,
    _service_id: int,
    _base_price: Decimal | None = None,
    _discount_percentage: Decimal | None = None,
    _estimated_duration: time | None = None,
    _description: str | None = None,
    _actor_user_id: int,
) -> Service:
    """Planned for post-v1; contract notes deactivate + recreate instead."""
    raise NotImplementedError


def serialize_service_status_toggle_response(service: Service) -> dict:
    """PATCH activate/deactivate response: ``id``, ``is_active``, ``updated_at``."""
    return {
        "id": service.id,
        "is_active": service.is_active,
        "updated_at": str(service.updated_at),
    }


def set_service_status_for_actor(
    db: Session,
    *,
    service_id: int,
    is_active: bool,
    actor_role: UserRole,
    actor_user_id: int,
) -> Service:
    """Set service active flag; main_admin only. Used for activate and deactivate."""
    if actor_role is not UserRole.MAIN_ADMIN:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only main admin can change service active status.",
            error_code="FORBIDDEN_SERVICE_ACTIVE_TOGGLE",
        )

    service = get_service_by_id(db, service_id=service_id)
    if service is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Service not found.",
            error_code="SERVICE_NOT_FOUND",
            details={"service_id": service_id},
        )

    if service.is_active is is_active:
        return service

    name = service.name
    vehicle_type = service.vehicle_type
    service_category = service.service_category

    service.is_active = is_active
    db.add(service)

    try:
        db.flush()
    except Exception as exc:
        if _ACTIVE_SERVICE_UNIQUE_UQ in str(exc):
            db.rollback()
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                message=("An active service with the same name, vehicle type, "
                         "and service category already exists."),
                error_code="DUPLICATE_ACTIVE_SERVICE",
                details={
                    "name": name,
                    "vehicle_type": vehicle_type,
                    "service_category": service_category,
                },
            ) from exc
        db.rollback()
        raise

    write_audit_log(
        db,
        action=("catalog.service.activate"
                if is_active else "catalog.service.deactivate"),
        entity_name="services",
        entity_id=str(service.id),
        actor_user_id=actor_user_id,
        franchise_id=None,
        payload={"is_active": service.is_active},
    )
    return service
