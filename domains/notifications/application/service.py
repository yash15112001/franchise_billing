from __future__ import annotations

import json
from urllib import error, request

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.audit.application.service import write_audit_log
from domains.bookings.infrastructure.models import Booking
from domains.customers.infrastructure.models import Customer
from domains.invoicing.infrastructure.models import Invoice
from domains.notifications.infrastructure.models import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationMessageType,
    OutboundNotification,
)
from domains.users.domain.access import UserRole
from domains.users.infrastructure.models import User
from foundation.config.settings import get_settings
from foundation.errors import AppError


def _require_interakt_config() -> tuple[str, str, str, str]:
    settings = get_settings()
    missing = []
    if not settings.interakt_api_key:
        missing.append("INTERAKT_API_KEY")
    if not settings.interakt_template_name:
        missing.append("INTERAKT_TEMPLATE_NAME")
    if missing:
        raise AppError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Interakt provider configuration is incomplete.",
            error_code="INTERAKT_CONFIG_MISSING",
            details={"missing_env_vars": missing},
        )
    return (
        settings.interakt_base_url.rstrip("/"),
        settings.interakt_api_key,
        settings.interakt_template_name,
        settings.interakt_template_language_code,
    )


def _split_recipient(phone_number: str) -> tuple[str, str]:
    settings = get_settings()
    digits = "".join(ch for ch in phone_number if ch.isdigit())
    if not digits:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="Phone number is required.",
            error_code="INVALID_WHATSAPP_PHONE_NUMBER",
        )
    default_country_code = settings.interakt_default_country_code
    country_digits = "".join(ch for ch in default_country_code if ch.isdigit())
    if len(digits) == 10:
        return default_country_code, digits
    if country_digits and digits.startswith(country_digits) and len(digits) > len(country_digits):
        return f"+{country_digits}", digits[len(country_digits):]
    if len(digits) < 10 or len(digits) > 15:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="Phone number must contain between 10 and 15 digits.",
            error_code="INVALID_WHATSAPP_PHONE_NUMBER",
            details={"phone_number": phone_number},
        )
    return default_country_code, digits


def _build_interakt_template_payload(
    *,
    country_code: str,
    phone_number: str,
    customer_name: str,
    booking_id: int,
    invoice_number: str,
    total_payable_amount: str,
) -> dict:
    _base_url, _api_key, template_name, template_language_code = _require_interakt_config()
    return {
        "countryCode": country_code,
        "phoneNumber": phone_number,
        "type": "Template",
        "callbackData": f"booking:{booking_id}|invoice:{invoice_number}",
        "template": {
            "name": template_name,
            "languageCode": template_language_code,
            "bodyValues": [
                customer_name,
                str(booking_id),
                invoice_number,
                total_payable_amount,
            ],
        },
    }


def _send_interakt_payload(payload: dict) -> dict:
    base_url, api_key, _template_name, _language_code = _require_interakt_config()
    url = f"{base_url}/v1/public/message/"
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            details = json.loads(raw)
        except json.JSONDecodeError:
            details = {"raw_response": raw}
        raise AppError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            message="Interakt rejected the message request.",
            error_code="INTERAKT_PROVIDER_ERROR",
            details=details,
        ) from exc
    except error.URLError as exc:
        raise AppError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            message="Failed to reach the Interakt provider.",
            error_code="INTERAKT_PROVIDER_UNREACHABLE",
            details={"reason": str(exc.reason)},
        ) from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            message="Interakt returned an invalid response.",
            error_code="INTERAKT_PROVIDER_INVALID_RESPONSE",
            details={"raw_response": raw},
        ) from exc


def _persist_notification(
    db: Session,
    *,
    actor: User,
    franchise_id: int | None,
    customer_id: int | None,
    invoice_id: int | None,
    recipient: str,
    text: str,
    response_payload: dict,
) -> OutboundNotification:
    provider_message_id = response_payload.get("id")

    notification = OutboundNotification(
        franchise_id=franchise_id,
        customer_id=customer_id,
        invoice_id=invoice_id,
        created_by_user_id=actor.id,
        channel=NotificationChannel.WHATSAPP,
        message_type=NotificationMessageType.TEXT,
        delivery_status=NotificationDeliveryStatus.SENT,
        recipient=recipient,
        body_text=text,
        provider_message_id=provider_message_id,
        provider_response=response_payload,
        error_message=None,
    )
    db.add(notification)
    db.flush()
    return notification


def _get_customer_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    customer_id: int,
) -> Customer:
    statement = select(Customer).where(
        Customer.id == customer_id,
        Customer.is_deleted.is_(False),
    )
    if actor_role is not UserRole.MAIN_ADMIN:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
            )
        statement = statement.where(Customer.franchise_id == actor_franchise_id)

    customer = db.scalar(statement)
    if customer is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Customer not found.",
            error_code="CUSTOMER_NOT_FOUND",
            details={"customer_id": customer_id},
        )
    return customer


def _get_booking_for_actor(
    db: Session,
    *,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    customer_id: int,
    booking_id: int,
) -> Booking:
    statement = select(Booking).where(
        Booking.id == booking_id,
        Booking.customer_id == customer_id,
        Booking.is_deleted.is_(False),
    )
    if actor_role is not UserRole.MAIN_ADMIN:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
            )
        statement = statement.where(Booking.franchise_id == actor_franchise_id)
    booking = db.scalar(statement)
    if booking is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Booking not found for this customer.",
            error_code="BOOKING_NOT_FOUND",
            details={"booking_id": booking_id, "customer_id": customer_id},
        )
    return booking


def _get_invoice_for_booking_for_actor(
    db: Session,
    *,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    booking: Booking,
) -> Invoice:
    statement = select(Invoice).where(
        Invoice.booking_id == booking.id,
        Invoice.is_deleted.is_(False),
    )
    if actor_role is not UserRole.MAIN_ADMIN:
        if actor_franchise_id is None:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Franchise context is required.",
                error_code="MISSING_FRANCHISE_CONTEXT",
            )
        statement = statement.where(Invoice.franchise_id == actor_franchise_id)
    invoice = db.scalar(statement)
    if invoice is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Invoice not found for this booking.",
            error_code="INVOICE_NOT_FOUND",
            details={"booking_id": booking.id},
        )
    return invoice


def send_booking_invoice_whatsapp_proof_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    customer_id: int,
    booking_id: int,
) -> OutboundNotification:
    customer = _get_customer_for_actor(
        db,
        actor=actor,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        customer_id=customer_id,
    )
    booking = _get_booking_for_actor(
        db,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        customer_id=customer.id,
        booking_id=booking_id,
    )
    invoice = _get_invoice_for_booking_for_actor(
        db,
        actor_role=actor_role,
        actor_franchise_id=actor_franchise_id,
        booking=booking,
    )
    recipient_input = customer.whatsapp_number or customer.mobile_number
    if not recipient_input:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Customer does not have a phone number for WhatsApp delivery.",
            error_code="CUSTOMER_WHATSAPP_NUMBER_MISSING",
            details={"customer_id": customer.id},
        )
    country_code, phone_number = _split_recipient(recipient_input)
    payload = _build_interakt_template_payload(
        country_code=country_code,
        phone_number=phone_number,
        customer_name=customer.full_name,
        booking_id=booking.id,
        invoice_number=invoice.invoice_number,
        total_payable_amount=str(invoice.total_payable_amount),
    )
    response_payload = _send_interakt_payload(payload)
    text = (
        f"Interakt invoice send for customer {customer.full_name}, "
        f"booking {booking.id}, invoice {invoice.invoice_number}."
    )
    notification = _persist_notification(
        db,
        actor=actor,
        franchise_id=customer.franchise_id,
        customer_id=customer.id,
        invoice_id=invoice.id,
        recipient=f"{country_code}{phone_number}",
        text=text,
        response_payload=response_payload,
    )
    write_audit_log(
        db,
        action="notification.interakt_proof_sent",
        entity_name="outbound_notifications",
        entity_id=str(notification.id),
        actor_user_id=actor.id,
        franchise_id=notification.franchise_id,
        payload={
            "channel": notification.channel.value,
            "customer_id": customer.id,
            "booking_id": booking.id,
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "recipient": f"{country_code}{phone_number}",
            "provider_message_id": notification.provider_message_id,
        },
    )
    return notification
