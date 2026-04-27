"""Booking & booking-item HTTP (see ``api_contracts.txt``)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from starlette import status as http_status

from domains.bookings.application.service import (
    create_booking_for_actor,
    create_booking_item_for_actor,
    get_booking_for_actor,
    get_booking_item_for_actor,
    list_booking_items_for_actor,
    list_bookings_for_actor,
    patch_booking_for_actor,
    put_booking_item_for_actor,
    replace_booking_items_for_actor,
    soft_delete_booking_for_actor,
)
from domains.bookings.domain.enums import BookingServiceStatus
from domains.bookings.interfaces.schemas import (
    CreateBookingItemRequest,
    CreateBookingRequest,
    PatchBookingRequest,
    PutBookingItemRequest,
    ReplaceBookingItemsRequest,
)
from domains.bookings.interfaces.serializers import (
    serialize_booking_detail,
    serialize_booking_item_create_response,
    serialize_booking_item_removed_response,
    serialize_booking_items_list_response,
    serialize_booking_items_replace_response,
    serialize_booking_patch_response,
)
from domains.users.domain.access import (
    CREATE_BOOKING,
    DELETE_BOOKINGS,
    MANAGE_BOOKING_ITEMS,
    UPDATE_BOOKINGS,
    VIEW_BOOKINGS,
    VIEW_BOOKING_ITEMS,
)
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.web.dependencies import UserContext, require_permissions
from foundation.web.responses import error_response, internal_error_response, success_response

router = APIRouter(prefix="/bookings", tags=["bookings"])
booking_items_router = APIRouter(prefix="/booking-items",
                                 tags=["booking-items"])

_CONTRACT = "docs/architecture/api_contracts.txt"


def _not_implemented(section: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Not implemented. See {_CONTRACT} ({section}).",
    )


# --- /bookings ---


@router.get("")
def list_bookings(
        franchise_id: int | None = Query(default=None),
        customer_id: int | None = Query(default=None),
        vehicle_id: int | None = Query(default=None),
        service_status: BookingServiceStatus | None = Query(default=None),
        created_by: int | None = Query(default=None),
        start_time: datetime | None = Query(default=None),
        end_time: datetime | None = Query(default=None),
        context: UserContext = Depends(require_permissions(VIEW_BOOKINGS)),
        db: Session = Depends(get_db),
) -> dict:
    """List bookings visible to the actor (franchise-scoped); returns full detail per row.

    **Query:** `franchise_id` (main admin), `customer_id`, `vehicle_id`, `service_status`,
    `created_by`, `start_time`, `end_time` (filters). **Auth:** `VIEW_BOOKINGS`.

    **Success:** 200 — `data`: array of booking detail objects (`serialize_booking_detail`).
    **Errors:** `MISSING_FRANCHISE_CONTEXT`, … AppError. 422 / 500.
    """
    try:
        booking_details = list_bookings_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            franchise_id=franchise_id,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            service_status=service_status,
            created_by=created_by,
            start_time=start_time,
            end_time=end_time,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Bookings fetched successfully.",
            data=[
                serialize_booking_detail(
                    booking=booking,
                    invoice=invoice,
                    services=services_config,
                    customer=customer,
                    vehicle=vehicle,
                    creator=created_by,
                ) for booking, invoice, services_config, customer, vehicle,
                created_by in booking_details
            ],
            status_code=http_status.HTTP_200_OK,
        )


@router.post("")
def create_booking(
        payload: CreateBookingRequest,
        context: UserContext = Depends(require_permissions(CREATE_BOOKING)),
        db: Session = Depends(get_db),
) -> dict:
    """Create a booking and associated invoice/lines per catalog rules.

    **Body:** `CreateBookingRequest` — franchise/customer/vehicle, `requested_services`, `gst_included`, etc.

    **Auth:** `CREATE_BOOKING`.

    **Success:** 201 — `data`: full booking detail (invoice, customer, vehicle embedded).
    **Errors:** validation / GST / catalog AppError codes. 422 / 500.
    """
    try:
        booking, invoice, services_by_id, customer, vehicle = (
            create_booking_for_actor(
                db,
                actor=context.user,
                actor_role=context.role,
                actor_franchise_id=context.franchise_id,
                actor_permissions=context.permissions,
                franchise_id=payload.franchise_id,
                customer_id=payload.customer_id,
                vehicle_id=payload.vehicle_id,
                requested_at=payload.requested_at,
                notes=payload.notes,
                requested_services=[
                    (requested_service.service_id, requested_service.qty)
                    for requested_service in payload.requested_services
                ],
                gst_included=payload.gst_included,
            ))
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        return success_response(
            message="Booking created successfully.",
            data=serialize_booking_detail(
                booking=booking,
                invoice=invoice,
                services=services_by_id,
                customer=customer,
                vehicle=vehicle,
                creator=context.user,
            ),
            status_code=http_status.HTTP_201_CREATED,
        )


# testing : partial done : deep testing pending
@router.put("/{booking_id}/items")
def replace_booking_items(
        booking_id: int,
        payload: ReplaceBookingItemsRequest,
        context: UserContext = Depends(
            require_permissions(MANAGE_BOOKING_ITEMS)),
        db: Session = Depends(get_db),
) -> dict:
    """Replace all line items for a booking; recalculates invoice totals.

    **Path:** `booking_id`. **Body:** `ReplaceBookingItemsRequest` — `items` (service_id, qty).

    **Auth:** `MANAGE_BOOKING_ITEMS`.

    **Success:** 200 — `data`: `{ booking_id, updated_at }` shape. **Errors:** `BOOKING_NOT_FOUND`, … 422 / 500.
    """
    try:
        booking, _invoice = replace_booking_items_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            booking_id=booking_id,
            requested_pairs=[(booking_item.service_id, booking_item.qty)
                             for booking_item in payload.items],
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
            message="Booking items replaced successfully.",
            data=serialize_booking_items_replace_response(booking),
            status_code=http_status.HTTP_200_OK,
        )


@router.patch("/{booking_id}")
def patch_booking(
        booking_id: int,
        payload: PatchBookingRequest,
        context: UserContext = Depends(require_permissions(UPDATE_BOOKINGS)),
        db: Session = Depends(get_db),
) -> dict:
    """Partial update: `service_status`, `notes` (see schema).

    **Path:** `booking_id`. **Body:** `PatchBookingRequest`.

    **Auth:** `UPDATE_BOOKINGS`.

    **Success:** 200 — `data`: `{ id, updated_at }`. **Errors:** `BOOKING_NOT_FOUND`, `EMPTY_BOOKING_PATCH`, … 422 / 500.
    """
    try:
        booking = patch_booking_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            booking_id=booking_id,
            service_status=payload.service_status,
            notes=payload.notes,
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
            message="Booking updated successfully.",
            data=serialize_booking_patch_response(booking),
            status_code=http_status.HTTP_200_OK,
        )


@router.get("/{booking_id}")
def get_booking(
        booking_id: int,
        context: UserContext = Depends(require_permissions(VIEW_BOOKINGS)),
        db: Session = Depends(get_db),
) -> dict:
    """Single booking with nested invoice, services, customer, vehicle, creator.

    **Path:** `booking_id`. **Auth:** `VIEW_BOOKINGS`.

    **Success:** 200 — `data`: booking detail. **Errors:** `BOOKING_NOT_FOUND`, … 422 / 500.
    """
    try:
        booking, invoice, services_config, customer, vehicle, created_by = get_booking_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            booking_id=booking_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Booking fetched successfully.",
            data=serialize_booking_detail(
                booking=booking,
                invoice=invoice,
                services=services_config,
                customer=customer,
                vehicle=vehicle,
                creator=created_by,
            ),
            status_code=http_status.HTTP_200_OK,
        )


@router.delete("/{booking_id}")
def delete_booking(
        booking_id: int,
        context: UserContext = Depends(require_permissions(DELETE_BOOKINGS)),
        db: Session = Depends(get_db),
) -> dict:
    """Soft-delete booking and its invoice/payment/booking-item tree."""
    try:
        booking = soft_delete_booking_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            booking_id=booking_id,
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
            message="Booking deleted successfully.",
            data={
                "id": booking.id,
                "is_deleted": booking.is_deleted,
                "updated_at": str(booking.updated_at),
            },
            status_code=http_status.HTTP_200_OK,
        )


# --- /booking-items ---


# testing : done : response structure needs to be fixed
@booking_items_router.get("")
def list_booking_items(
        booking_id: int | None = Query(default=None),
        service_id: int | None = Query(default=None),
        context: UserContext = Depends(
            require_permissions(VIEW_BOOKING_ITEMS)),
        db: Session = Depends(get_db),
) -> dict:
    """List booking line items; optional filter by `booking_id` / `service_id`.

    When `booking_id` is set, nested booking context may be included in serialized rows.

    **Auth:** `VIEW_BOOKING_ITEMS`. **Success:** 200. **Errors:** AppError. 422 / 500.
    """
    try:
        items = list_booking_items_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            booking_id=booking_id,
            service_id=service_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Booking items fetched successfully.",
            data=serialize_booking_items_list_response(
                db,
                actor=context.user,
                actor_role=context.role,
                actor_franchise_id=context.franchise_id,
                items=items,
                nested=booking_id is not None,
            ),
            status_code=http_status.HTTP_200_OK,
        )


@booking_items_router.post("")
def create_booking_item(
        payload: CreateBookingItemRequest,
        context: UserContext = Depends(
            require_permissions(MANAGE_BOOKING_ITEMS)),
        db: Session = Depends(get_db),
) -> dict:
    """Add a line to a booking (updates invoice).

    **Body:** `CreateBookingItemRequest` — `booking_id`, `service_id`, `qty`.

    **Auth:** `MANAGE_BOOKING_ITEMS`. **Success:** 201 — created line summary. **Errors:** AppError. 422 / 500.
    """
    try:
        item = create_booking_item_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            booking_id=payload.booking_id,
            service_id=payload.service_id,
            qty=payload.qty,
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
            message="Booking item placed successfully.",
            data=serialize_booking_item_create_response(item),
            status_code=http_status.HTTP_201_CREATED,
        )


@booking_items_router.put("/{booking_item_id}")
def put_booking_item(
        booking_item_id: int,
        payload: PutBookingItemRequest,
        context: UserContext = Depends(
            require_permissions(MANAGE_BOOKING_ITEMS)),
        db: Session = Depends(get_db),
) -> dict:
    """Set line quantity (`qty`); `qty: 0` removes the line and updates invoice.

    **Path:** `booking_item_id`. **Body:** `PutBookingItemRequest` — `qty`.

    **Auth:** `MANAGE_BOOKING_ITEMS`. **Success:** 200 — update or removal payload. **Errors:** AppError. 422 / 500.
    """
    try:
        item, booking, removed_item_id = put_booking_item_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            booking_item_id=booking_item_id,
            qty=payload.qty,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        return error_response(exc)
    except Exception:
        db.rollback()
        return internal_error_response()
    else:
        if item is not None:
            return success_response(
                message="Booking item updated successfully.",
                data=serialize_booking_item_create_response(item),
                status_code=http_status.HTTP_200_OK,
            )
        assert removed_item_id is not None
        return success_response(
            message="Booking item removed successfully.",
            data=serialize_booking_item_removed_response(
                booking=booking,
                removed_item_id=removed_item_id,
            ),
            status_code=http_status.HTTP_200_OK,
        )


# testing : done : response structure needs to be fixed
@booking_items_router.get("/{booking_item_id}")
def get_booking_item(
        booking_item_id: int,
        context: UserContext = Depends(
            require_permissions(VIEW_BOOKING_ITEMS)),
        db: Session = Depends(get_db),
) -> dict:
    """Fetch one booking line by id (serialized list-response shape).

    **Path:** `booking_item_id`. **Auth:** `VIEW_BOOKING_ITEMS`.

    **Success:** 200. **Errors:** `BOOKING_ITEM_NOT_FOUND`, … 422 / 500.
    """
    try:
        item = get_booking_item_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            booking_item_id=booking_item_id,
        )
    except AppError as exc:
        return error_response(exc)
    except Exception:
        return internal_error_response()
    else:
        return success_response(
            message="Booking item fetched successfully.",
            data=serialize_booking_items_list_response(
                db,
                actor=context.user,
                actor_role=context.role,
                actor_franchise_id=context.franchise_id,
                items=[item],
                nested=True,
            ),
            status_code=http_status.HTTP_200_OK,
        )
