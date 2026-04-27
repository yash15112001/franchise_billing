"""Booking application services.

Implement domain logic here. HTTP contracts:
``docs/architecture/api_contracts.txt`` (Booking, BookingItem).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from domains.audit.application.service import write_audit_log
from domains.bookings.domain.enums import BookingServiceStatus
from domains.bookings.infrastructure.models import Booking, BookingItem
from domains.catalog.infrastructure.models import Service
from domains.customers.infrastructure.models import Customer, Vehicle
from domains.franchises.application.service import get_franchise_for_actor
from domains.invoicing.domain.enums import InvoicePaymentStatus
from domains.invoicing.infrastructure.models import Invoice
from domains.payments.infrastructure.models import Payment
from domains.users.domain.access import CREATE_NON_GST_INVOICE, UserRole
from domains.users.infrastructure.models import User
from foundation.errors import AppError

logger = logging.getLogger(__name__)

_MONEY_QUANT = Decimal("0.01")
# Standard GST rate for services (exclusive); adjust if product rules change.
_GST_RATE = Decimal("0.18")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _invoice_number(
    *,
    requested_at: datetime,
    franchise_id: int,
    booking_id: int,
) -> str:
    """Human-readable invoice number: INV-{DDMMYYYY}-{franchise_id}-{booking_id}."""
    date_part = requested_at.strftime("%d%m%Y")
    return f"INV-{date_part}-{franchise_id}-{booking_id}"


def _service_net_unit_price(service: Service) -> Decimal:
    discount = service.discount_percentage
    factor = Decimal(1) - (discount / Decimal(100))
    return _money(service.base_price * factor)


def _invoice_totals_from_pairs(
    requested_pairs: Sequence[tuple[int, int]],
    services_by_id: dict[int, Service],
    gst_included: bool,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return ``(total_base_amount, gst_amount, total_payable_amount)``."""

    total_base_amount = Decimal("0.00")
    for service_id, qty in requested_pairs:
        service_net_unit_price = _service_net_unit_price(
            services_by_id[service_id])
        total_base_amount += _money(service_net_unit_price * Decimal(qty))
    total_base_amount = _money(total_base_amount)
    if gst_included:
        gst_amount = _money(total_base_amount * _GST_RATE)
        total_payable_amount = _money(total_base_amount + gst_amount)
    else:
        gst_amount = Decimal("0.00")
        total_payable_amount = total_base_amount
    return total_base_amount, gst_amount, total_payable_amount


def _payment_status_from_paid_and_payable(
        paid: Decimal, payable: Decimal) -> InvoicePaymentStatus:
    paid_q = _money(paid)
    payable_q = _money(payable)
    if payable_q <= Decimal("0.00"):
        return InvoicePaymentStatus.PENDING
    if paid_q <= Decimal("0.00"):
        return InvoicePaymentStatus.PENDING
    if paid_q >= payable_q:
        return InvoicePaymentStatus.COMPLETE
    return InvoicePaymentStatus.PARTIAL


def _apply_invoice_totals_from_booking_items(
    db: Session,
    booking: Booking,
    invoice: Invoice,
) -> None:
    """Recompute invoice amounts and payment status from persisted ``booking_items`` rows."""

    booking_items = list(
        db.scalars(
            select(BookingItem).where(
                BookingItem.booking_id == booking.id,
                BookingItem.is_deleted.is_(False),
            )).all())

    pairs_after = [(booking_item.service_id, booking_item.qty)
                   for booking_item in booking_items]

    booking_item_service_ids = {service_id for service_id, _ in pairs_after}

    services = list(
        db.scalars(
            select(Service).where(Service.id.in_(booking_item_service_ids))).
        all()) if booking_item_service_ids else []

    services_by_id: dict[int, Service] = {
        service.id: service
        for service in services
    }

    total_base_amount, gst_amount, total_payable_amount = _invoice_totals_from_pairs(
        pairs_after,
        services_by_id,
        invoice.gst_included,
    )

    invoice.total_base_amount = total_base_amount
    invoice.gst_amount = gst_amount
    invoice.total_payable_amount = total_payable_amount

    invoice.payment_status = _payment_status_from_paid_and_payable(
        invoice.total_paid_amount,
        total_payable_amount,
    )


# TODO : dont send franchise_id in payload, derive it from customer
def create_booking_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    actor_permissions: set[str],
    franchise_id: int | None,
    customer_id: int,
    vehicle_id: int,
    requested_at: datetime,
    notes: str | None,
    requested_services: Sequence[tuple[int, int]],
    gst_included: bool,
) -> tuple[Booking, Invoice, dict[int, Service], Customer, Vehicle]:
    """Create a booking, line items, and initial invoice. Returns entities for HTTP serialization.

    ``created_by`` on the booking is always ``actor.id``. Duplicate ``service_id`` values and
    per-line ``qty`` are validated on :class:`CreateBookingRequest`; this layer still enforces
    domain rules for franchise scope, catalog, and vehicle/service compatibility.

    ``get_franchise_for_actor`` ensures the franchise exists **and** that the actor may
    operate on it (main admin: any id; franchise users: only their franchise). A bare FK on
    insert would only guarantee a row exists in ``franchises``, not authorization.
    """

    if not gst_included and CREATE_NON_GST_INVOICE not in actor_permissions:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            message="You are not allowed to create bookings without GST.",
            error_code="FORBIDDEN_NON_GST_BOOKING",
            details={},
        )

    resolved_franchise_id: int
    if actor_role is UserRole.MAIN_ADMIN:
        if franchise_id is None:
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="franchise_id is required when creating a booking.",
                error_code="MISSING_FRANCHISE_ID",
                details={},
            )
        resolved_franchise_id = franchise_id
    else:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
                details={},
            )
        resolved_franchise_id = actor_franchise_id
        if franchise_id is not None and franchise_id != actor_franchise_id:
            logger.info(
                "Ignored body franchise_id for booking create; "
                "franchise users always book in their franchise. "
                "actor_user_id=%s requested_franchise_id=%s actor_franchise_id=%s",
                actor.id,
                franchise_id,
                actor_franchise_id,
            )

    get_franchise_for_actor(
        db,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=resolved_franchise_id,
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
            message="Customer does not belong to this franchise.",
            error_code="CUSTOMER_FRANCHISE_MISMATCH",
            details={
                "customer_id": customer_id,
                "franchise_id": resolved_franchise_id,
            },
        )

    vehicle = db.scalar(
        select(Vehicle).where(
            Vehicle.id == vehicle_id,
            Vehicle.is_deleted.is_(False),
        ))
    if vehicle is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Vehicle not found.",
            error_code="VEHICLE_NOT_FOUND",
            details={"vehicle_id": vehicle_id},
        )
    if vehicle.customer_id != customer_id:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Vehicle does not belong to the given customer.",
            error_code="VEHICLE_CUSTOMER_MISMATCH",
            details={
                "vehicle_id": vehicle_id,
                "customer_id": customer_id,
            },
        )

    requested_pairs = list(requested_services)

    service_ids = [service_id for service_id, _ in requested_pairs]
    services = list(
        db.scalars(select(Service).where(Service.id.in_(service_ids))).all())

    services_by_id: dict[int, Service] = {s.id: s for s in services}
    missing_service_ids = [
        service_id for service_id in service_ids
        if service_id not in services_by_id
    ]

    if missing_service_ids:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="One or more services were not found.",
            error_code="SERVICE_NOT_FOUND",
            details={"service_ids": missing_service_ids},
        )

    # Catalog services are defined per vehicle_type; enforce match so wrong-class work is not booked.
    vehicle_type_lower = vehicle.vehicle_type.strip().lower()
    for service_id, service_info in services_by_id.items():
        if not service_info.is_active:
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Inactive services cannot be added to a booking.",
                error_code="SERVICE_INACTIVE",
                details={"service_id": service_id},
            )
        if service_info.vehicle_type.strip().lower() != vehicle_type_lower:
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                message=
                ("Service vehicle type does not match the vehicle type for this booking."
                 ),
                error_code="SERVICE_VEHICLE_TYPE_MISMATCH",
                details={
                    "service_id": service_id,
                    "service_vehicle_type": service_info.vehicle_type,
                    "vehicle_type": vehicle.vehicle_type,
                },
            )

    total_base_amount, gst_amount, total_payable_amount = _invoice_totals_from_pairs(
        requested_pairs, services_by_id, gst_included)

    booking = Booking(
        franchise_id=resolved_franchise_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        requested_at=requested_at,
        service_status=BookingServiceStatus.PENDING,
        created_by=actor.id,
        notes=notes,
    )
    db.add(booking)
    db.flush()

    for service_id, qty in requested_pairs:
        booking.items.append(BookingItem(
            service_id=service_id,
            qty=qty,
        ))

    db.flush()

    invoice_number = _invoice_number(
        requested_at=requested_at,
        franchise_id=resolved_franchise_id,
        booking_id=booking.id,
    )
    invoice = Invoice(
        invoice_number=invoice_number,
        franchise_id=resolved_franchise_id,
        booking_id=booking.id,
        gst_included=gst_included,
        gst_amount=gst_amount,
        total_base_amount=total_base_amount,
        total_payable_amount=total_payable_amount,
        total_paid_amount=Decimal("0.00"),
        payment_status=InvoicePaymentStatus.PENDING,
    )
    db.add(invoice)
    db.flush()

    write_audit_log(
        db,
        action="booking.create",
        entity_name="bookings",
        entity_id=str(booking.id),
        actor_user_id=actor.id,
        franchise_id=resolved_franchise_id,
        payload={
            "customer_id": customer_id,
            "vehicle_id": vehicle_id,
            "invoice_number": invoice_number,
        },
    )

    return booking, invoice, services_by_id, customer, vehicle


def _query_bookings(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int | None = None,
    booking_id: int | None = None,
    booking_ids: list[int] | None = None,
    customer_id: int | None = None,
    vehicle_id: int | None = None,
    service_status: BookingServiceStatus | None = None,
    created_by: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    order_desc_by_created: bool = True,
) -> list[Booking]:
    if booking_ids is not None and len(booking_ids) == 0:
        return []

    if actor_role is UserRole.MAIN_ADMIN:
        if franchise_id is not None:
            get_franchise_for_actor(
                db,
                actor_role=actor_role,
                actor_franchise_id=actor_franchise_id,
                franchise_id=franchise_id,
            )
    else:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
                details={},
            )
        if franchise_id is not None and franchise_id != actor_franchise_id:
            logger.info(
                "Ignored franchise_id for booking query; "
                "franchise users only see their franchise. "
                "actor_user_id=%s requested_franchise_id=%s actor_franchise_id=%s",
                actor.id,
                franchise_id,
                actor_franchise_id,
            )

    statement = select(Booking).options(selectinload(Booking.items)).where(
        Booking.is_deleted.is_(False))
    if order_desc_by_created:
        statement = statement.order_by(Booking.created_at.desc())

    if actor_role is UserRole.MAIN_ADMIN:
        if franchise_id is not None:
            statement = statement.where(Booking.franchise_id == franchise_id)
    else:
        statement = statement.where(Booking.franchise_id == actor_franchise_id)

    if booking_ids is not None:
        statement = statement.where(Booking.id.in_(booking_ids))
    elif booking_id is not None:
        statement = statement.where(Booking.id == booking_id)
    if customer_id is not None:
        statement = statement.where(Booking.customer_id == customer_id)
    if vehicle_id is not None:
        statement = statement.where(Booking.vehicle_id == vehicle_id)
    if service_status is not None:
        statement = statement.where(Booking.service_status == service_status)
    if created_by is not None:
        statement = statement.where(Booking.created_by == created_by)
    if start_time is not None:
        statement = statement.where(Booking.requested_at >= start_time)
    if end_time is not None:
        statement = statement.where(Booking.requested_at <= end_time)

    return list(db.scalars(statement).all())


def _query_booking_items(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    booking_item_id: int | None = None,
    booking_id: int | None = None,
    service_id: int | None = None,
) -> list[BookingItem]:
    """Return booking lines visible to the actor (``Booking`` franchise scope), with optional filters."""

    if actor_role is not UserRole.MAIN_ADMIN:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
                details={},
            )

    statement = (select(BookingItem).join(
        Booking, BookingItem.booking_id == Booking.id))
    statement = statement.where(
        Booking.is_deleted.is_(False),
        BookingItem.is_deleted.is_(False),
    )
    if actor_role is not UserRole.MAIN_ADMIN:
        statement = statement.where(Booking.franchise_id == actor_franchise_id)

    if booking_item_id is not None:
        statement = statement.where(BookingItem.id == booking_item_id)
    if booking_id is not None:
        statement = statement.where(BookingItem.booking_id == booking_id)
    if service_id is not None:
        statement = statement.where(BookingItem.service_id == service_id)

    statement = statement.order_by(BookingItem.booking_id, BookingItem.id)
    return list(db.scalars(statement).all())


def list_booking_items_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    booking_id: int | None,
    service_id: int | None,
) -> list[BookingItem]:
    """Rows visible to the actor for ``GET /booking-items`` (serialization in HTTP layer)."""

    return _query_booking_items(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        booking_item_id=None,
        booking_id=booking_id,
        service_id=service_id,
    )


def get_booking_item_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    booking_item_id: int,
) -> BookingItem:
    """Single line for ``GET /booking-items/{{id}}`` (serialization in HTTP layer)."""

    rows = _query_booking_items(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        booking_item_id=booking_item_id,
        booking_id=None,
        service_id=None,
    )
    if not rows:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Booking item not found.",
            error_code="BOOKING_ITEM_NOT_FOUND",
            details={"booking_item_id": booking_item_id},
        )
    return rows[0]


def _collate_booking_rows(
    db: Session,
    bookings: list[Booking],
) -> list[tuple[Booking, Invoice | None, dict[int, Service], Customer, Vehicle,
                User | None]]:
    if not bookings:
        return []

    booking_ids = [b.id for b in bookings]
    invoices_list = list(
        db.scalars(
            select(Invoice).where(
                Invoice.booking_id.in_(booking_ids),
                Invoice.is_deleted.is_(False),
            )).all())
    invoices_by_booking_id: dict[int, Invoice] = {
        invoice.booking_id: invoice
        for invoice in invoices_list
    }

    customer_ids = {booking.customer_id for booking in bookings}
    vehicle_ids = {booking.vehicle_id for booking in bookings}
    user_ids = {booking.created_by for booking in bookings}
    service_ids: set[int] = set()
    for booking in bookings:
        for booking_item in booking.items:
            service_ids.add(booking_item.service_id)

    customers_by_id = {
        customer.id: customer
        for customer in db.scalars(
            select(Customer).where(Customer.id.in_(customer_ids))).all()
    }
    vehicles_by_id = {
        vehicle.id: vehicle
        for vehicle in db.scalars(
            select(Vehicle).where(Vehicle.id.in_(vehicle_ids))).all()
    }
    users_by_id = {
        user.id: user
        for user in db.scalars(select(User).where(User.id.in_(
            user_ids))).all()
    }
    services_by_id: dict[int, Service] = {}
    if service_ids:
        for service in db.scalars(
                select(Service).where(Service.id.in_(service_ids))).all():
            services_by_id[service.id] = service

    out: list[tuple[Booking, Invoice | None, dict[int, Service], Customer,
                    Vehicle, User | None]] = []

    for booking in bookings:
        customer = customers_by_id.get(booking.customer_id)
        vehicle = vehicles_by_id.get(booking.vehicle_id)
        if customer is None or vehicle is None:
            logger.warning(
                "Skipping booking %s: missing customer or vehicle row.",
                booking.id,
            )
            continue
        invoice = invoices_by_booking_id.get(booking.id)
        booking_items = {
            booking_item.service_id: services_by_id[booking_item.service_id]
            for booking_item in booking.items
            if booking_item.service_id in services_by_id
        }
        out.append((booking, invoice, booking_items, customer, vehicle,
                    users_by_id.get(booking.created_by)))
    return out


def list_bookings_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    franchise_id: int | None,
    customer_id: int | None,
    vehicle_id: int | None,
    service_status: BookingServiceStatus | None,
    created_by: int | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> list[tuple[Booking, Invoice | None, dict[int, Service], Customer, Vehicle,
                User | None]]:
    bookings = _query_bookings(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        franchise_id=franchise_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        service_status=service_status,
        created_by=created_by,
        start_time=start_time,
        end_time=end_time,
        order_desc_by_created=True,
    )
    return _collate_booking_rows(db, bookings)


def get_booking_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    booking_id: int,
) -> tuple[Booking, Invoice | None, dict[int, Service], Customer, Vehicle, User
           | None]:
    """Return one scoped booking or :class:`AppError` ``BOOKING_NOT_FOUND``."""
    bookings = _query_bookings(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        booking_id=booking_id,
        order_desc_by_created=False,
    )
    if not bookings:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Booking not found.",
            error_code="BOOKING_NOT_FOUND",
            details={"booking_id": booking_id},
        )
    rows = _collate_booking_rows(db, bookings)
    if not rows:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Booking not found.",
            error_code="BOOKING_NOT_FOUND",
            details={"booking_id": booking_id},
        )
    return rows[0]


def create_booking_item_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    booking_id: int,
    service_id: int,
    qty: int,
) -> tuple[BookingItem | None, Booking, int | None]:
    """Upsert one booking line or remove it when ``qty`` is 0, then recompute invoice.

    For ``qty >= 1``, ``qty`` is the desired count for that service (same idea as
    ``PUT /bookings/{booking_id}/items``). For ``qty == 0``, an existing line for
    ``service_id`` is deleted; if none exists, ``BOOKING_ITEM_NOT_FOUND`` is raised.

    Returns ``(item, booking, removed_item_id)``. After a removal, ``item`` is
    ``None`` and ``removed_item_id`` is set; otherwise ``removed_item_id`` is ``None``.
    """

    bookings = _query_bookings(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        booking_id=booking_id,
        order_desc_by_created=False,
    )
    if not bookings:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Booking not found.",
            error_code="BOOKING_NOT_FOUND",
            details={"booking_id": booking_id},
        )
    booking = bookings[0]

    vehicle = db.get(Vehicle, booking.vehicle_id)
    if vehicle is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Vehicle not found.",
            error_code="VEHICLE_NOT_FOUND",
            details={"vehicle_id": booking.vehicle_id},
        )

    invoice = db.scalar(
        select(Invoice).where(
            Invoice.booking_id == booking.id,
            Invoice.is_deleted.is_(False),
        ))
    if invoice is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Invoice not found for this booking.",
            error_code="INVOICE_NOT_FOUND",
            details={"booking_id": booking.id},
        )

    service = db.get(Service, service_id)
    if service is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="One or more services were not found.",
            error_code="SERVICE_NOT_FOUND",
            details={"service_ids": [service_id]},
        )
    if not service.is_active:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Inactive services cannot be added to a booking.",
            error_code="SERVICE_INACTIVE",
            details={"service_id": service_id},
        )
    vehicle_type_lower = vehicle.vehicle_type.strip().lower()
    if service.vehicle_type.strip().lower() != vehicle_type_lower:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=
            ("Service vehicle type does not match the vehicle type for this booking."
             ),
            error_code="SERVICE_VEHICLE_TYPE_MISMATCH",
            details={
                "service_id": service_id,
                "service_vehicle_type": service.vehicle_type,
                "vehicle_type": vehicle.vehicle_type,
            },
        )

    existing = db.scalar(
        select(BookingItem).where(
            BookingItem.booking_id == booking.id,
            BookingItem.service_id == service_id,
            BookingItem.is_deleted.is_(False),
        ))
    if existing is not None:
        existing.qty = qty
        item = existing
    else:
        item = BookingItem(service_id=service_id, qty=qty)
        booking.items.append(item)

    db.flush()
    _apply_invoice_totals_from_booking_items(db, booking, invoice)
    db.flush()
    db.refresh(booking)
    db.refresh(item)

    write_audit_log(
        db,
        action="booking.item_create",
        entity_name="booking_items",
        entity_id=str(item.id),
        actor_user_id=actor.id,
        franchise_id=booking.franchise_id,
        payload={
            "booking_id": booking.id,
            "service_id": service_id,
            "qty": qty,
        },
    )
    return item


def put_booking_item_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    booking_item_id: int,
    qty: int,
) -> tuple[BookingItem | None, Booking, int | None]:
    """Set ``qty`` on a line by primary key, or delete when ``qty`` is 0; recompute invoice."""

    row = db.scalar(
        select(BookingItem).where(
            BookingItem.id == booking_item_id,
            BookingItem.is_deleted.is_(False),
        ))
    if row is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Booking item not found.",
            error_code="BOOKING_ITEM_NOT_FOUND",
            details={"booking_item_id": booking_item_id},
        )

    bookings = _query_bookings(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        booking_id=row.booking_id,
        order_desc_by_created=False,
    )
    if not bookings:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Booking not found.",
            error_code="BOOKING_NOT_FOUND",
            details={"booking_id": row.booking_id},
        )
    booking = bookings[0]

    invoice = db.scalar(
        select(Invoice).where(
            Invoice.booking_id == booking.id,
            Invoice.is_deleted.is_(False),
        ))
    if invoice is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Invoice not found for this booking.",
            error_code="INVOICE_NOT_FOUND",
            details={"booking_id": booking.id},
        )

    if qty == 0:
        removed_id = row.id
        db.delete(row)
        db.flush()
        _apply_invoice_totals_from_booking_items(db, booking, invoice)
        db.flush()
        db.refresh(booking)

        write_audit_log(
            db,
            action="booking.item_delete",
            entity_name="booking_items",
            entity_id=str(removed_id),
            actor_user_id=actor.id,
            franchise_id=booking.franchise_id,
            payload={
                "booking_id": booking.id,
                "booking_item_id": booking_item_id,
            },
        )
        return None, booking, removed_id

    row.qty = qty
    db.flush()
    _apply_invoice_totals_from_booking_items(db, booking, invoice)
    db.flush()
    db.refresh(booking)
    db.refresh(row)

    write_audit_log(
        db,
        action="booking.item_update",
        entity_name="booking_items",
        entity_id=str(row.id),
        actor_user_id=actor.id,
        franchise_id=booking.franchise_id,
        payload={
            "booking_id": booking.id,
            "qty": qty,
        },
    )
    return row, booking, None


def replace_booking_items_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    booking_id: int,
    requested_pairs: Sequence[tuple[int, int]],
) -> tuple[Booking, Invoice]:
    new_map = {service_id: qty for service_id, qty in requested_pairs}

    bookings = _query_bookings(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        booking_id=booking_id,
        order_desc_by_created=False,
    )
    if not bookings:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Booking not found.",
            error_code="BOOKING_NOT_FOUND",
            details={"booking_id": booking_id},
        )
    booking = bookings[0]

    vehicle = db.get(Vehicle, booking.vehicle_id)
    if vehicle is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Vehicle not found.",
            error_code="VEHICLE_NOT_FOUND",
            details={"vehicle_id": booking.vehicle_id},
        )

    invoice = db.scalar(
        select(Invoice).where(
            Invoice.booking_id == booking.id,
            Invoice.is_deleted.is_(False),
        ))
    if invoice is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Invoice not found for this booking.",
            error_code="INVOICE_NOT_FOUND",
            details={"booking_id": booking.id},
        )

    service_ids = list(new_map.keys())
    services = list(
        db.scalars(select(Service).where(Service.id.in_(service_ids))).all())
    services_by_id: dict[int, Service] = {
        service.id: service
        for service in services
    }

    missing_service_ids = [
        service_id for service_id in service_ids
        if service_id not in services_by_id
    ]
    if missing_service_ids:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="One or more services were not found.",
            error_code="SERVICE_NOT_FOUND",
            details={"service_ids": missing_service_ids},
        )

    vehicle_type_lower = vehicle.vehicle_type.strip().lower()
    for service_id in service_ids:
        service_info = services_by_id[service_id]
        if not service_info.is_active:
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Inactive services cannot be added to a booking.",
                error_code="SERVICE_INACTIVE",
                details={"service_id": service_id},
            )
        if service_info.vehicle_type.strip().lower() != vehicle_type_lower:
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                message=
                ("Service vehicle type does not match the vehicle type for this booking."
                 ),
                error_code="SERVICE_VEHICLE_TYPE_MISMATCH",
                details={
                    "service_id": service_id,
                    "service_vehicle_type": service_info.vehicle_type,
                    "vehicle_type": vehicle.vehicle_type,
                },
            )

    existing_by_service_id = {
        booking_item.service_id: booking_item
        for booking_item in list(booking.items)
    }
    for service_id in list(existing_by_service_id.keys()):
        if service_id not in new_map:
            db.delete(existing_by_service_id[service_id])

    db.flush()
    existing_by_service_id = {
        booking_item.service_id: booking_item
        for booking_item in list(booking.items)
    }
    for service_id, qty in new_map.items():
        if service_id in existing_by_service_id:
            if existing_by_service_id[service_id].qty != qty:
                existing_by_service_id[service_id].qty = qty
        else:
            booking.items.append(BookingItem(service_id=service_id, qty=qty))

    db.flush()

    _apply_invoice_totals_from_booking_items(db, booking, invoice)

    db.flush()
    db.refresh(booking)
    db.refresh(invoice)

    write_audit_log(
        db,
        action="booking.items_replace",
        entity_name="bookings",
        entity_id=str(booking.id),
        actor_user_id=actor.id,
        franchise_id=booking.franchise_id,
        payload={
            "invoice_id": invoice.id,
        },
    )
    return booking, invoice


def patch_booking_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    booking_id: int,
    service_status: BookingServiceStatus | None,
    notes: str | None,
) -> Booking:
    if service_status is None and notes is None:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="At least one field must be provided to update.",
            error_code="EMPTY_BOOKING_PATCH",
            details={},
        )

    bookings = _query_bookings(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        booking_id=booking_id,
        order_desc_by_created=False,
    )
    if not bookings:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Booking not found.",
            error_code="BOOKING_NOT_FOUND",
            details={"booking_id": booking_id},
        )
    booking = bookings[0]

    if service_status is not None:
        booking.service_status = service_status
    if notes is not None:
        booking.notes = notes

    db.flush()
    db.refresh(booking)

    write_audit_log(
        db,
        action="booking.update",
        entity_name="bookings",
        entity_id=str(booking.id),
        actor_user_id=actor.id,
        franchise_id=booking.franchise_id,
        payload={"fields": "partial"},
    )
    return booking


def soft_delete_booking_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    booking_id: int,
) -> Booking:
    bookings = _query_bookings(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        booking_id=booking_id,
        order_desc_by_created=False,
    )
    if not bookings:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Booking not found.",
            error_code="BOOKING_NOT_FOUND",
            details={"booking_id": booking_id},
        )
    booking = bookings[0]

    _soft_delete_booking_tree(db, booking=booking)

    write_audit_log(
        db,
        action="booking.delete",
        entity_name="bookings",
        entity_id=str(booking.id),
        actor_user_id=actor.id,
        franchise_id=booking.franchise_id,
        payload={"is_deleted": True},
    )
    return booking


def _soft_delete_booking_tree(
    db: Session,
    *,
    booking: Booking,
) -> tuple[Booking, Invoice | None, list[BookingItem], list[Payment]]:
    """Soft-delete a booking plus its invoice, payments, and booking items."""

    if booking.is_deleted is False:
        booking_items = list(
            db.scalars(
                select(BookingItem).where(
                    BookingItem.booking_id == booking.id,
                    BookingItem.is_deleted.is_(False),
                )).all())
        for item in booking_items:
            item.is_deleted = True

        invoice = db.scalar(
            select(Invoice).where(
                Invoice.booking_id == booking.id,
                Invoice.is_deleted.is_(False),
            ))
        if invoice is not None:
            payments = list(
                db.scalars(
                    select(Payment).where(
                        Payment.invoice_id == invoice.id,
                        Payment.is_deleted.is_(False),
                    )).all())
            for payment in payments:
                payment.is_deleted = True
            invoice.is_deleted = True

        booking.is_deleted = True
        db.flush()

    return booking, invoice, booking_items, payments
