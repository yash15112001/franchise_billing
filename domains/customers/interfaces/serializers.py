"""HTTP/API response shapes for customer domain entities."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.bookings.infrastructure.models import BookingItem
from domains.catalog.infrastructure.models import Service
from domains.customers.domain.customer_list_row import CustomerListRow
from domains.customers.infrastructure.models import Customer, Vehicle
from domains.invoicing.infrastructure.models import Invoice
from domains.payments.infrastructure.models import Payment


def serialize_customer_core(customer: Customer) -> dict:
    return {
        "id": customer.id,
        "franchise_id": customer.franchise_id,
        "full_name": customer.full_name,
        "email": customer.email,
        "type": customer.type.value,
        "mobile_number": customer.mobile_number,
        "whatsapp_number": customer.whatsapp_number,
    }


def serialize_customer_row(
    customer: Customer,
    *,
    last_visit_time: Any | None,
    total_visits: int,
    total_spending: Decimal,
) -> dict:
    """Single row: core customer fields plus booking/invoice aggregates (flat)."""
    out = serialize_customer_core(customer)
    out["last_visit_time"] = (str(last_visit_time)
                              if last_visit_time is not None else None)
    out["total_visits"] = total_visits
    out["total_spending"] = str(total_spending)
    return out


def serialize_customer_list_row(row: CustomerListRow) -> dict:
    """One JSON object — core customer fields plus aggregate fields (same shape as get)."""
    return serialize_customer_row(
        row.customer,
        last_visit_time=row.last_visit_time,
        total_visits=row.total_visits,
        total_spending=row.total_spending,
    )


def serialize_customer_patch_response(customer: Customer) -> dict:
    return {
        "customer_id": customer.id,
        "updated_at": str(customer.updated_at),
    }


def serialize_vehicle_row(
    vehicle: Vehicle,
    *,
    customer: Customer | None = None,
) -> dict:
    base = {
        "id": vehicle.id,
        "name": vehicle.name,
        "customer_id": vehicle.customer_id,
        "franchise_id": vehicle.franchise_id,
        "registration_number": vehicle.registration_number,
        "colour": vehicle.color,
        "model": vehicle.model,
        "vehicle_type": vehicle.vehicle_type,
    }
    if customer is not None:
        base["customer_info"] = {
            "id": customer.id,
            "full_name": customer.full_name,
            "mobile_number": customer.mobile_number,
        }
    return base


def serialize_vehicle_list_response(
    db: Session,
    vehicles: list[Vehicle],
) -> list[dict]:
    """Batch-load owning customers and build list payloads."""
    if not vehicles:
        return []
    cust_ids = {v.customer_id for v in vehicles}
    customers: dict[int, Customer] = {}
    if cust_ids:
        for c in db.scalars(select(Customer).where(
                Customer.id.in_(cust_ids))).all():
            customers[c.id] = c
    return [
        serialize_vehicle_row(v, customer=customers.get(v.customer_id))
        for v in vehicles
    ]


def serialize_vehicle_detail_response(
    db: Session,
    vehicle: Vehicle | None,
) -> dict | None:
    """Load owning customer and build the single-vehicle API payload; empty input → no payload."""
    if vehicle is None:
        return None
    customer = db.get(Customer, vehicle.customer_id)
    return serialize_vehicle_row(vehicle, customer=customer)


def serialize_vehicle_patch_response(vehicle: Vehicle) -> dict:
    return {
        "id": vehicle.id,
        "updated_at": str(vehicle.updated_at),
    }


# --- Customer history (nested bookings / invoice / line items) ---


def serialize_service_snapshot_for_history(
    svc: Service | None,
    line: BookingItem,
) -> dict:
    if svc is not None:
        return {
            "id": svc.id,
            "name": svc.name,
            "vehicle_type": svc.vehicle_type,
            "service_category": svc.service_category,
            "base_price": str(svc.base_price),
            "discount_percentage": str(svc.discount_percentage),
            "estimated_duration": svc.estimated_duration.isoformat(),
            "description": svc.description,
            "created_at": str(svc.created_at),
            "updated_at": str(svc.updated_at),
        }
    return {
        "service_id": line.service_id,
        "qty": line.qty,
    }


def serialize_invoice_payments_for_history(
    db: Session,
    invoice_id: int,
) -> list[dict]:
    rows = db.scalars(
        select(Payment).where(Payment.invoice_id == invoice_id).order_by(
            Payment.created_at.asc())).all()
    return [{
        "id": p.id,
        "amount": str(p.amount),
        "mode": p.mode.value,
        "verified_by": p.verified_by,
        "reference_number": p.reference_number,
        "created_at": str(p.created_at),
        "updated_at": str(p.updated_at),
    } for p in rows]


def serialize_invoice_detail_for_history(
    db: Session,
    inv: Invoice | None,
) -> dict | None:
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
        "payments": serialize_invoice_payments_for_history(db, inv.id),
    }


def serialize_booking_line_item_for_history(
    line: BookingItem,
    services: dict[int, Service],
) -> dict:
    svc = services.get(line.service_id)
    return {
        "id": line.id,
        "service_id": line.service_id,
        "qty": line.qty,
        "service": serialize_service_snapshot_for_history(svc, line),
    }
