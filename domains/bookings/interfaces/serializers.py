"""HTTP response shapes for booking APIs."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.bookings.infrastructure.models import Booking, BookingItem
from domains.catalog.infrastructure.models import Service
from domains.customers.infrastructure.models import Customer, Vehicle
from domains.customers.interfaces.serializers import (
    serialize_customer_core,
    serialize_vehicle_row,
)
from domains.invoicing.infrastructure.models import Invoice
from domains.users.application.service import serialize_user_summary
from domains.users.domain.access import UserRole
from domains.users.infrastructure.models import User


def serialize_booking_items_list_response(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    items: list[BookingItem],
    nested: bool,
) -> dict:
    from domains.bookings.application.service import (
        _collate_booking_rows,
        _query_bookings,
    )

    if not items:
        return []

    if not nested:
        line_sids = {booking_item.service_id for booking_item in items}
        services_by_id: dict[int, Service] = {}
        if line_sids:
            for svc in db.scalars(
                    select(Service).where(Service.id.in_(line_sids))).all():
                services_by_id[svc.id] = svc
        return [
            serialize_booking_item_minimal_row(
                booking_item,
                services_by_id.get(booking_item.service_id),
            ) for booking_item in items
        ]

    unique_bids = list({booking_item.booking_id for booking_item in items})
    bookings = _query_bookings(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        booking_ids=unique_bids,
        order_desc_by_created=False,
    )
    collated = _collate_booking_rows(db, bookings)
    detail_by_bid: dict[int, dict] = {}
    for row in collated:
        booking, invoice, services, customer, vehicle, creator = row
        detail_by_bid[booking.id] = serialize_booking_detail(
            booking=booking,
            invoice=invoice,
            services=services,
            customer=customer,
            vehicle=vehicle,
            creator=creator,
        )

    line_sids = {booking_item.service_id for booking_item in items}
    line_services: dict[int, Service] = {}
    if line_sids:
        for svc in db.scalars(
                select(Service).where(Service.id.in_(line_sids))).all():
            line_services[svc.id] = svc

    out: list[dict] = []
    for booking_item in items:
        svc = line_services.get(booking_item.service_id)
        nested_svc = (serialize_booking_service(svc) if svc is not None else {
            "service_id": booking_item.service_id,
            "qty": booking_item.qty,
        })
        out.append({
            "id": booking_item.id,
            "booking_id": booking_item.booking_id,
            "service_id": booking_item.service_id,
            "qty": booking_item.qty,
            "service": nested_svc,
            "booking": detail_by_bid[booking_item.booking_id],
        })
    return out


def serialize_booking_service(svc: Service) -> dict:
    return {
        "name": svc.name,
        "vehicle_type": svc.vehicle_type,
        "service_category": svc.service_category,
        "base_price": str(svc.base_price),
        "discount_percentage": str(svc.discount_percentage),
        "estimated_duration": svc.estimated_duration.isoformat(),
        "description": svc.description,
    }


def serialize_booking_item_minimal_row(
    item: BookingItem,
    service: Service | None,
) -> dict:
    """Minimal booking line for ``GET /booking-items`` (no nested booking)."""

    nested = (serialize_booking_service(service) if service is not None else {
        "service_id": item.service_id,
        "qty": item.qty,
    })
    return {
        "id": item.id,
        "booking_id": item.booking_id,
        "service_id": item.service_id,
        "qty": item.qty,
        "service": nested,
    }


def serialize_booking_items_payload(
    items: Sequence[BookingItem],
    services: dict[int, Service],
) -> list[dict]:
    out: list[dict] = []
    for booking_item in items:
        service = services.get(booking_item.service_id)
        nested = (serialize_booking_service(service)
                  if service is not None else {
                      "service_id": booking_item.service_id,
                      "qty": booking_item.qty,
                  })
        out.append({
            "id": booking_item.id,
            "service_id": booking_item.service_id,
            "qty": booking_item.qty,
            "service": nested,
        })
    return out


def serialize_invoice_detail_for_history(inv: Invoice | None) -> dict | None:
    if inv is None:
        return None
    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "franchise_id": inv.franchise_id,
        "booking_id": inv.booking_id,
        "gst_included": inv.gst_included,
        "gst_amount": str(inv.gst_amount),
        "total_base_amount": str(inv.total_base_amount),
        "total_payable_amount": str(inv.total_payable_amount),
        "total_paid_amount": str(inv.total_paid_amount),
        "payment_status": inv.payment_status.value,
        "created_at": str(inv.created_at),
        "updated_at": str(inv.updated_at),
    }


def serialize_booking_item_create_response(item: BookingItem) -> dict:
    """Response for ``POST /booking-items`` (``id``, ``booking_id``, ``updated_at``)."""

    return {
        "id":
        item.id,
        "booking_id":
        item.booking_id,
        "updated_at":
        str(item.updated_at) if item.updated_at is not None else None,
    }


def serialize_booking_item_removed_response(
    *,
    booking: Booking,
    removed_item_id: int,
) -> dict:
    """Same envelope after ``qty: 0`` removed a line (``id`` is the deleted row id)."""

    return {
        "id":
        removed_item_id,
        "booking_id":
        booking.id,
        "updated_at":
        str(booking.updated_at) if booking.updated_at is not None else None,
    }


def serialize_booking_items_replace_response(booking: Booking) -> dict:
    """Response for ``PUT /bookings/{booking_id}/items`` (``booking_id``, ``updated_at``)."""

    return {
        "booking_id":
        booking.id,
        "updated_at":
        str(booking.updated_at) if booking.updated_at is not None else None,
    }


def serialize_booking_patch_response(booking: Booking) -> dict:
    """Response for ``PATCH /bookings/{booking_id}`` (``api_contracts``: ``id``, ``updated_at``)."""

    return {
        "id":
        booking.id,
        "updated_at":
        str(booking.updated_at) if booking.updated_at is not None else None,
    }


def serialize_booking_detail(
    *,
    booking: Booking,
    invoice: Invoice | None,
    services: dict[int, Service],
    customer: Customer,
    vehicle: Vehicle,
    creator: User | None,
) -> dict:
    return {
        "id": booking.id,
        "franchise_id": booking.franchise_id,
        "customer_id": booking.customer_id,
        "vehicle_id": booking.vehicle_id,
        "requested_at": booking.requested_at.isoformat(),
        "notes": booking.notes,
        "created_at": booking.created_at.isoformat(),
        "updated_at": booking.updated_at.isoformat(),
        "service_status": booking.service_status.value,
        "booking_items":
        serialize_booking_items_payload(booking.items, services),
        "vehicle": serialize_vehicle_row(vehicle),
        "created_by":
        serialize_user_summary(creator) if creator is not None else {
            "id": booking.created_by
        },
        "customer": serialize_customer_core(customer),
        "invoice": serialize_invoice_detail_for_history(invoice),
    }
