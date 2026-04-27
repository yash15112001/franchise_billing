from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from domains.audit.application.service import write_audit_log
from domains.bookings.application.service import _soft_delete_booking_tree
from domains.bookings.infrastructure.models import Booking
from domains.catalog.infrastructure.models import Service
from domains.customers.domain.customer_list_row import CustomerListRow
from domains.customers.infrastructure.models import Customer, CustomerType, Vehicle
from domains.customers.interfaces.serializers import (
    serialize_booking_line_item_for_history,
    serialize_customer_core,
    serialize_invoice_detail_for_history,
    serialize_vehicle_row,
)
from domains.franchises.infrastructure.models import FranchiseReview
from domains.franchises.infrastructure.models import Franchise
from domains.invoicing.infrastructure.models import Invoice
from domains.users.application.service import serialize_user_summary
from domains.users.domain.access import UserRole
from domains.users.infrastructure.models import User
from foundation.errors import AppError

logger = logging.getLogger(__name__)

_TWO = Decimal("0.01")

_CUSTOMER_UNIQUE_MOBILE_UQ = "uq_customer_mobile"


def _money(value: Decimal) -> Decimal:
    return value.quantize(_TWO, rounding=ROUND_HALF_UP)


def _optional_customer_query_text(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    return s if s else None


def _query_customers(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    customer_id: int | None = None,
    franchise_id: int | None = None,
    search: str | None = None,
    full_name: str | None = None,
    customer_type: CustomerType | None = None,
    mobile_number: str | None = None,
    whatsapp_number: str | None = None,
    email: str | None = None,
) -> list[Customer]:
    """Internal: franchise scope first, then optional id / list filters (see ``list_franchises_for_actor``)."""
    search = _optional_customer_query_text(search)
    full_name = _optional_customer_query_text(full_name)
    mobile_number = _optional_customer_query_text(mobile_number)
    whatsapp_number = _optional_customer_query_text(whatsapp_number)
    email = _optional_customer_query_text(email)

    statement = select(Customer).where(Customer.is_deleted.is_(False))
    if actor_role is UserRole.MAIN_ADMIN:
        if franchise_id is not None:
            statement = statement.where(Customer.franchise_id == franchise_id)
    else:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
            )
        if franchise_id is not None and franchise_id != actor_franchise_id:
            logger.info(
                "Ignored body franchise_id for customer get; "
                "franchise_admin/staff always gets customers from their franchise. "
                "actor_user_id=%s requested_franchise_id=%s actor_franchise_id=%s",
                actor.id,
                franchise_id,
                actor_franchise_id,
            )
        statement = statement.where(
            Customer.franchise_id == actor_franchise_id)

    if customer_id is not None:
        statement = statement.where(Customer.id == customer_id)
    if search:
        q = f"%{search}%"
        statement = statement.where(
            or_(
                Customer.full_name.ilike(q),
                Customer.mobile_number.ilike(q),
                Customer.whatsapp_number.ilike(q),
                Customer.email.ilike(q),
            ))
    if full_name:
        statement = statement.where(Customer.full_name.ilike(f"%{full_name}%"))
    if customer_type is not None:
        statement = statement.where(Customer.type == customer_type)
    if mobile_number:
        statement = statement.where(
            Customer.mobile_number.ilike(f"%{mobile_number}%"))
    if whatsapp_number:
        statement = statement.where(
            Customer.whatsapp_number.ilike(f"%{whatsapp_number}%"))
    if email:
        statement = statement.where(Customer.email.ilike(f"%{email}%"))
    statement = statement.order_by(Customer.id.asc())
    return list(db.scalars(statement).all())


def list_customers_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int | None,
    search: str | None,
    full_name: str | None,
    customer_type: CustomerType | None,
    mobile_number: str | None,
    whatsapp_number: str | None,
    email: str | None,
) -> list[CustomerListRow]:
    """Customers visible to the actor with aggregates for list responses."""
    customers = _query_customers(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        customer_id=None,
        franchise_id=franchise_id,
        search=search,
        full_name=full_name,
        customer_type=customer_type,
        mobile_number=mobile_number,
        whatsapp_number=whatsapp_number,
        email=email,
    )
    if not customers:
        return []
    agg = customer_aggregates_map(db, [c.id for c in customers])
    default: tuple[Any | None, int, Decimal] = (None, 0, Decimal("0.00"))
    return [
        CustomerListRow(
            customer=c,
            last_visit_time=agg.get(c.id, default)[0],
            total_visits=agg.get(c.id, default)[1],
            total_spending=agg.get(c.id, default)[2],
        ) for c in customers
    ]


def get_customer_list_row_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    customer_id: int,
) -> CustomerListRow:
    """One scoped customer plus aggregates; uses :func:`_query_customers` like list/get."""
    rows = _query_customers(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        customer_id=customer_id,
    )
    if not rows:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Customer not found.",
            error_code="CUSTOMER_NOT_FOUND",
            details={"customer_id": customer_id},
        )
    customer = rows[0]
    agg = customer_aggregates_map(db, [customer.id])
    default: tuple[Any | None, int, Decimal] = (None, 0, Decimal("0.00"))
    return CustomerListRow(
        customer=customer,
        last_visit_time=agg.get(customer.id, default)[0],
        total_visits=agg.get(customer.id, default)[1],
        total_spending=agg.get(customer.id, default)[2],
    )


# TODO : revisit when booking module is completed
def customer_aggregates_map(
    db: Session,
    customer_ids: list[int],
) -> dict[int, tuple[Any, int, Decimal]]:
    """``(last_visit_time, total_visits, total_spending)`` per customer id.

    No bookings: ``last_visit_time`` is ``None``, ``total_visits`` is ``0``; spending
    still comes from invoices for that customer when present, else ``0.00``.

    Uses two queries: (1) booking stats grouped by ``Booking.customer_id``; (2) invoice
    totals grouped by the same, joining ``Invoice`` → ``Booking`` (invoices have no
    ``customer_id``; customer is on the booking). Booking counts and invoice sums stay
    separate so visit counts are not conflated with money.
    """
    if not customer_ids:
        return {}

    booking_rows = db.execute(
        select(
            Booking.customer_id,
            func.max(Booking.created_at),
            func.count(Booking.id),
        ).where(
            Booking.customer_id.in_(customer_ids),
            Booking.is_deleted.is_(False),
        ).group_by(
            Booking.customer_id)).all()
    booking_map: dict[int, tuple[Any, int]] = {
        row[0]: (row[1], int(row[2]))
        for row in booking_rows
    }

    spend_rows = db.execute(
        select(
            Booking.customer_id,
            func.coalesce(func.sum(Invoice.total_payable_amount), 0),
        ).select_from(Booking).join(
            Invoice,
            Invoice.booking_id == Booking.id,
        ).where(
            Booking.customer_id.in_(customer_ids),
            Booking.is_deleted.is_(False),
            Invoice.is_deleted.is_(False),
        ).group_by(
            Booking.customer_id)).all()
    spend_map = {row[0]: _money(Decimal(str(row[1]))) for row in spend_rows}

    zero = Decimal("0.00")
    out: dict[int, tuple[Any, int, Decimal]] = {}
    for cid in customer_ids:
        b = booking_map.get(cid)
        if b is None:
            out[cid] = (None, 0, spend_map.get(cid, zero))
        else:
            last_visit, visit_count = b
            out[cid] = (last_visit, visit_count, spend_map.get(cid, zero))
    return out


def create_customer_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int | None,
    full_name: str,
    mobile_number: str,
    whatsapp_number: str,
    email: str | None,
    customer_type: CustomerType = CustomerType.NEW,
) -> Customer:
    resolved_franchise_id = None
    if actor_role is UserRole.MAIN_ADMIN:
        if franchise_id is None:
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="franchise_id is required when creating a customer.",
                error_code="MISSING_FRANCHISE_ID",
            )
        resolved_franchise_id = franchise_id
        franchise = db.scalar(
            select(Franchise).where(
                Franchise.id == resolved_franchise_id,
                Franchise.is_deleted.is_(False),
            ))
        if franchise is None:
            raise AppError(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Franchise not found.",
                error_code="FRANCHISE_NOT_FOUND",
                details={"franchise_id": resolved_franchise_id},
            )
    else:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="You must belong to a franchise to create customers.",
                error_code="MISSING_ACTOR_FRANCHISE",
            )
        resolved_franchise_id = actor_franchise_id
        if franchise_id is not None and franchise_id != actor_franchise_id:
            logger.info(
                "Ignored body franchise_id for customer create; "
                "franchise_admin/staff always create in their franchise. "
                "actor_user_id=%s requested_franchise_id=%s actor_franchise_id=%s",
                actor.id,
                franchise_id,
                actor_franchise_id,
            )

    item = Customer(
        franchise_id=resolved_franchise_id,
        full_name=full_name,
        mobile_number=mobile_number,
        whatsapp_number=whatsapp_number,
        email=email,
        type=customer_type,
    )
    db.add(item)

    try:
        db.flush()
    except IntegrityError as exc:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message=
            "A customer with this mobile number already exists for this franchise.",
            error_code="DUPLICATE_CUSTOMER_MOBILE",
            details={
                "franchise_id": resolved_franchise_id,
                "mobile_number": mobile_number,
            },
        ) from exc

    write_audit_log(
        db,
        action="customer.create",
        entity_name="customers",
        entity_id=str(item.id),
        actor_user_id=actor.id,
        franchise_id=resolved_franchise_id,
        payload={
            "full_name": item.full_name,
            "mobile_number": item.mobile_number,
            "type": item.type.value,
        },
    )

    return item


def update_customer_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    customer_id: int,
    full_name: str | None,
    email: str | None,
    mobile_number: str | None,
    whatsapp_number: str | None,
    customer_type: CustomerType | None,
) -> Customer:
    statement = select(Customer).where(
        Customer.id == customer_id,
        Customer.is_deleted.is_(False),
    )
    if actor_role is UserRole.MAIN_ADMIN:
        pass
    else:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
            )
        statement = statement.where(
            Customer.franchise_id == actor_franchise_id)
    customer = db.scalar(statement)
    if customer is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Customer not found.",
            error_code="CUSTOMER_NOT_FOUND",
            details={"customer_id": customer_id},
        )
    if (full_name is None and email is None and mobile_number is None
            and whatsapp_number is None and customer_type is None):
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="At least one field must be provided to update.",
            error_code="EMPTY_CUSTOMER_PATCH",
        )
    if full_name is not None:
        customer.full_name = full_name
    if email is not None:
        customer.email = email
    if mobile_number is not None:
        customer.mobile_number = mobile_number
    if whatsapp_number is not None:
        customer.whatsapp_number = whatsapp_number
    if customer_type is not None:
        customer.type = customer_type
    db.add(customer)
    try:
        db.flush()
    except Exception as exc:
        if _CUSTOMER_UNIQUE_MOBILE_UQ in str(exc):
            db.rollback()
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                message=
                ("A customer with this mobile number already exists for this franchise."
                 ),
                error_code="DUPLICATE_CUSTOMER_MOBILE",
                details={
                    "franchise_id": customer.franchise_id,
                    "mobile_number": mobile_number,
                },
            ) from exc
        db.rollback()
        raise
    write_audit_log(
        db,
        action="customer.update",
        entity_name="customers",
        entity_id=str(customer.id),
        actor_user_id=actor.id,
        franchise_id=customer.franchise_id,
        payload={"fields": "partial"},
    )
    return customer


# TODO : revisit when booking module is completed
def get_customer_history_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    customer_id: int,
) -> dict:
    """Scoped customer via :func:`_query_customers`, aggregates via :func:`customer_aggregates_map`, then bookings tree."""
    rows = _query_customers(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        customer_id=customer_id,
    )
    if not rows:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Customer not found.",
            error_code="CUSTOMER_NOT_FOUND",
            details={"customer_id": customer_id},
        )
    customer = rows[0]
    agg = customer_aggregates_map(db, [customer.id])
    default: tuple[Any | None, int, Decimal] = (None, 0, Decimal("0.00"))
    lv, tv, ts = agg.get(customer.id, default)

    bookings = list(
        db.scalars(
            select(Booking).where(
                Booking.customer_id == customer.id,
                Booking.is_deleted.is_(False),
            ).options(
                selectinload(Booking.items)).order_by(
                    Booking.created_at.desc())).all())
    vehicle_ids = {b.vehicle_id for b in bookings}
    vehicles: dict[int, Vehicle] = {}
    if vehicle_ids:
        for v in db.scalars(
                select(Vehicle).where(Vehicle.id.in_(vehicle_ids))).all():
            vehicles[v.id] = v
    service_ids: set[int] = set()
    for b in bookings:
        for li in b.items:
            service_ids.add(li.service_id)
    services: dict[int, Service] = {}
    if service_ids:
        for s in db.scalars(
                select(Service).where(Service.id.in_(service_ids))).all():
            services[s.id] = s

    booking_ids = [b.id for b in bookings]
    invoices_by_booking: dict[int, Invoice] = {}
    if booking_ids:
        for inv in db.scalars(
                select(Invoice).where(
                    Invoice.booking_id.in_(booking_ids),
                    Invoice.is_deleted.is_(False),
                )).all():
            bid = inv.booking_id
            if bid is not None and bid not in invoices_by_booking:
                invoices_by_booking[bid] = inv

    created_by_ids = {b.created_by for b in bookings}
    users_by_id: dict[int, User] = {}
    if created_by_ids:
        for u in db.scalars(select(User).where(
                User.id.in_(created_by_ids))).all():
            users_by_id[u.id] = u

    booking_payload: list[dict] = []
    for b in bookings:
        veh = vehicles.get(b.vehicle_id)
        inv = invoices_by_booking.get(b.id)
        creator = users_by_id.get(b.created_by)
        items = [
            serialize_booking_line_item_for_history(li, services)
            for li in b.items
        ]
        booking_payload.append({
            "id":
            b.id,
            "franchise_id":
            b.franchise_id,
            "customer_id":
            b.customer_id,
            "vehicle_id":
            b.vehicle_id,
            "requested_at":
            b.requested_at.isoformat(),
            "service_status":
            b.service_status.value,
            "notes":
            b.notes,
            "created_at":
            b.created_at.isoformat(),
            "updated_at":
            b.updated_at.isoformat(),
            "vehicle":
            serialize_vehicle_row(veh, customer=customer)
            if veh is not None else None,
            "booking_items":
            items,
            "created_by":
            serialize_user_summary(creator) if creator is not None else {
                "id": b.created_by
            },
            "invoice":
            serialize_invoice_detail_for_history(db, inv),
        })

    return {
        "customer_info": serialize_customer_core(customer),
        "last_visit_time": str(lv) if lv else None,
        "total_visits": tv,
        "total_spending": str(ts),
        "bookings": booking_payload,
    }


# --- Vehicles ---


def _query_vehicles(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    vehicle_id: int | None = None,
    franchise_id: int | None = None,
    search: str | None = None,
    name: str | None = None,
    customer_id: int | None = None,
    registration_number: str | None = None,
    vehicle_type: str | None = None,
    color: str | None = None,
    model: str | None = None,
) -> list[Vehicle]:
    """Franchise scope first, then optional id / list filters (see ``_query_customers``)."""
    search = _optional_customer_query_text(search)
    name = _optional_customer_query_text(name)
    registration_number = _optional_customer_query_text(registration_number)
    vehicle_type = _optional_customer_query_text(vehicle_type)
    color = _optional_customer_query_text(color)
    model = _optional_customer_query_text(model)

    statement = select(Vehicle).join(Customer,
                                     Customer.id == Vehicle.customer_id)
    statement = statement.where(Vehicle.is_deleted.is_(False))

    if actor_role is UserRole.MAIN_ADMIN:
        if franchise_id is not None:
            statement = statement.where(Vehicle.franchise_id == franchise_id)
    else:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
            )
        if franchise_id is not None and franchise_id != actor_franchise_id:
            logger.info(
                "Ignored franchise_id query param for vehicles; "
                "franchise_admin/staff only see their franchise. "
                "actor_user_id=%s requested_franchise_id=%s actor_franchise_id=%s",
                actor.id,
                franchise_id,
                actor_franchise_id,
            )
        statement = statement.where(Vehicle.franchise_id == actor_franchise_id)

    if vehicle_id is not None:
        statement = statement.where(Vehicle.id == vehicle_id)
    if customer_id is not None:
        statement = statement.where(Vehicle.customer_id == customer_id)
    if search:
        q = f"%{search}%"
        statement = statement.where(
            or_(
                Vehicle.name.ilike(q),
                Vehicle.registration_number.ilike(q),
                Vehicle.model.ilike(q),
                Vehicle.vehicle_type.ilike(q),
                Customer.full_name.ilike(q),
                Customer.mobile_number.ilike(q),
            ))
    if name:
        statement = statement.where(Vehicle.name.ilike(f"%{name}%"))
    if registration_number:
        statement = statement.where(
            Vehicle.registration_number.ilike(f"%{registration_number}%"))
    if vehicle_type:
        statement = statement.where(
            Vehicle.vehicle_type.ilike(f"%{vehicle_type}%"))
    if color:
        statement = statement.where(Vehicle.color.ilike(f"%{color}%"))
    if model:
        statement = statement.where(Vehicle.model.ilike(f"%{model}%"))
    statement = statement.order_by(Vehicle.registration_number.asc(),
                                   Vehicle.id.asc())
    return list(db.scalars(statement).all())


def list_vehicles_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    search: str | None,
    name: str | None,
    customer_id: int | None,
    franchise_id: int | None,
    registration_number: str | None,
    vehicle_type: str | None,
    color: str | None,
    model: str | None,
) -> list[Vehicle]:
    return _query_vehicles(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        vehicle_id=None,
        franchise_id=franchise_id,
        search=search,
        name=name,
        customer_id=customer_id,
        registration_number=registration_number,
        vehicle_type=vehicle_type,
        color=color,
        model=model,
    )


def get_vehicle_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    vehicle_id: int,
) -> Vehicle | None:
    rows = _query_vehicles(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        vehicle_id=vehicle_id,
    )
    if not rows:
        return None
    return rows[0]


def create_vehicle_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    customer_id: int,
    franchise_id: int | None,
    name: str | None,
    registration_number: str,
    colour: str,
    model: str,
    vehicle_type: str,
) -> Vehicle:
    if actor_role is UserRole.MAIN_ADMIN:
        if franchise_id is None:
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="franchise_id is required when creating a vehicle.",
                error_code="MISSING_FRANCHISE_ID",
            )
        resolved_franchise_id = franchise_id
    else:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="You must belong to a franchise to create customers.",
                error_code="MISSING_ACTOR_FRANCHISE",
            )
        resolved_franchise_id = actor_franchise_id
        if franchise_id is not None and franchise_id != actor_franchise_id:
            logger.info(
                "Ignored body franchise_id for vehicle create; "
                "franchise_admin/staff always create in their franchise. "
                "actor_user_id=%s requested_franchise_id=%s actor_franchise_id=%s",
                actor.id,
                franchise_id,
                actor_franchise_id,
            )

    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.is_deleted.is_(False),
        ))
    if customer is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Customer not found.",
            error_code="CUSTOMER_NOT_FOUND",
            details={"customer_id": customer_id},
        )
    if customer.franchise_id != resolved_franchise_id:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Customer franchise_id must match vehicle franchise_id.",
            error_code="CUSTOMER_FRANCHISE_MISMATCH",
        )

    v = Vehicle(
        customer_id=customer_id,
        franchise_id=resolved_franchise_id,
        name=name,
        registration_number=registration_number,
        color=colour,
        model=model,
        vehicle_type=vehicle_type,
    )
    db.add(v)
    try:
        db.flush()
    except IntegrityError as exc:
        print(exc)
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message=
            ("A vehicle with this registration number already exists for this customer."
             ),
            error_code="DUPLICATE_VEHICLE_REGISTRATION",
            details={
                "customer_id": customer_id,
                "registration_number": registration_number,
            },
        ) from exc
    write_audit_log(
        db,
        action="vehicle.create",
        entity_name="vehicles",
        entity_id=str(v.id),
        actor_user_id=actor.id,
        franchise_id=resolved_franchise_id,
        payload={"registration_number": registration_number},
    )
    return v


def update_vehicle_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    vehicle_id: int,
    name: str | None,
    vehicle_type: str | None,
    colour: str | None,
    model: str | None,
) -> Vehicle:
    statement = select(Vehicle).where(
        Vehicle.id == vehicle_id,
        Vehicle.is_deleted.is_(False),
    )
    if actor_role is UserRole.MAIN_ADMIN:
        pass
    else:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
            )
        statement = statement.where(Vehicle.franchise_id == actor_franchise_id)
    vehicle = db.scalar(statement)
    if vehicle is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Vehicle not found.",
            error_code="VEHICLE_NOT_FOUND",
            details={"vehicle_id": vehicle_id},
        )
    if (name is None and vehicle_type is None and colour is None
            and model is None):
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="At least one field must be provided to update.",
            error_code="EMPTY_VEHICLE_PATCH",
        )
    if name is not None:
        vehicle.name = name
    if vehicle_type is not None:
        vehicle.vehicle_type = vehicle_type
    if colour is not None:
        vehicle.color = colour
    if model is not None:
        vehicle.model = model
    db.add(vehicle)
    db.flush()
    write_audit_log(
        db,
        action="vehicle.update",
        entity_name="vehicles",
        entity_id=str(vehicle.id),
        actor_user_id=actor.id,
        franchise_id=vehicle.franchise_id,
        payload={"fields": "partial"},
    )
    return vehicle


def soft_delete_customer_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    customer_id: int,
) -> Customer:
    rows = _query_customers(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        customer_id=customer_id,
    )
    if not rows:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Customer not found.",
            error_code="CUSTOMER_NOT_FOUND",
            details={"customer_id": customer_id},
        )

    customer = rows[0]
    vehicles = list(
        db.scalars(
            select(Vehicle).where(
                Vehicle.customer_id == customer.id,
                Vehicle.is_deleted.is_(False),
            )).all())
    for vehicle in vehicles:
        soft_delete_vehicle_for_actor(
            db,
            actor=actor,
            actor_role=actor_role,
            actor_franchise_id=actor_franchise_id,
            vehicle_id=vehicle.id,
        )

    reviews = list(
        db.scalars(
            select(FranchiseReview).where(
                FranchiseReview.customer_id == customer.id,
                FranchiseReview.is_deleted.is_(False),
            )).all())
    for review in reviews:
        review.is_deleted = True

    if customer.is_deleted is False:
        customer.is_deleted = True
        db.flush()

    write_audit_log(
        db,
        action="customer.delete",
        entity_name="customers",
        entity_id=str(customer.id),
        actor_user_id=actor.id,
        franchise_id=customer.franchise_id,
        payload={"is_deleted": True},
    )
    return customer


def soft_delete_vehicle_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    vehicle_id: int,
) -> Vehicle:
    rows = _query_vehicles(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        vehicle_id=vehicle_id,
    )
    if not rows:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Vehicle not found.",
            error_code="VEHICLE_NOT_FOUND",
            details={"vehicle_id": vehicle_id},
        )

    vehicle = rows[0]
    bookings = list(
        db.scalars(
            select(Booking).where(
                Booking.vehicle_id == vehicle.id,
                Booking.is_deleted.is_(False),
            )).all())

    for booking in bookings:
        _soft_delete_booking_tree(db, booking=booking)

    if vehicle.is_deleted is False:
        vehicle.is_deleted = True
        db.flush()

    write_audit_log(
        db,
        action="vehicle.delete",
        entity_name="vehicles",
        entity_id=str(vehicle.id),
        actor_user_id=actor.id,
        franchise_id=vehicle.franchise_id,
        payload={"is_deleted": True},
    )
    return vehicle
