from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from urllib import error, request

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile, status
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

logger = logging.getLogger(__name__)
INVOICE_PDF_S3_PREFIX = "invoice-pdfs"
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_MULTI_UNDERSCORE_RE = re.compile(r"_+")

def _normalize_invoice_pdf_name(value: str | None) -> str:
    stem = Path(value or "invoice").stem.lower().strip()
    stem = stem.replace(" ", "_")
    stem = _NON_ALNUM_RE.sub("_", stem)
    stem = _MULTI_UNDERSCORE_RE.sub("_", stem).strip("_")
    return stem or "invoice"


def _build_invoice_pdf_s3_key(
    *,
    booking_id: int,
    invoice_number: str,
    original_filename: str | None,
) -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    normalized_file_name = _normalize_invoice_pdf_name(original_filename)
    file_name = (
        f"invoice_{booking_id}_{invoice_number}_{normalized_file_name}_{timestamp}.pdf"
    )
    return f"{INVOICE_PDF_S3_PREFIX}/{file_name}"


def upload_invoice_pdf_and_get_presigned_url(
    *,
    booking_id: int,
    invoice_number: str,
    pdf_bytes: bytes,
    original_filename: str | None,
    content_type: str,
) -> tuple[str, str]:
    settings = get_settings()
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    object_key = _build_invoice_pdf_s3_key(
        booking_id=booking_id,
        invoice_number=invoice_number,
        original_filename=original_filename,
    )
    try:
        s3_client.put_object(
            Bucket=settings.s3_bucket_name,
            Key=object_key,
            Body=pdf_bytes,
            ContentType=content_type,
        )
        presigned_url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.s3_bucket_name,
                "Key": object_key,
            },
            ExpiresIn=settings.s3_presigned_url_expires_seconds,
        )
    except (BotoCoreError, ClientError) as exc:
        raise AppError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            message="Failed to upload invoice PDF to S3.",
            error_code="S3_UPLOAD_FAILED",
            details={"reason": str(exc)},
        ) from exc

    logger.info(
        "Uploaded invoice PDF to S3 for booking_id=%s bucket=%s key=%s",
        booking_id,
        settings.s3_bucket_name,
        object_key,
    )
    return object_key, presigned_url


def prepare_invoice_pdf_upload(
    *,
    booking_id: int,
    invoice_number: str,
    invoice_pdf: UploadFile,
) -> tuple[str, str, str]:
    if invoice_pdf.content_type != "application/pdf":
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="invoice_pdf must be a PDF file.",
            error_code="INVALID_INVOICE_PDF_CONTENT_TYPE",
            details={"content_type": invoice_pdf.content_type},
        )

    pdf_file_name = Path(invoice_pdf.filename or "invoice.pdf").name or "invoice.pdf"
    pdf_bytes = invoice_pdf.file.read()
    object_key, presigned_url = upload_invoice_pdf_and_get_presigned_url(
        booking_id=booking_id,
        invoice_number=invoice_number,
        pdf_bytes=pdf_bytes,
        original_filename=invoice_pdf.filename,
        content_type=invoice_pdf.content_type,
    )
    logger.info(
        "Generated invoice PDF presigned URL for booking_id=%s key=%s url=%s",
        booking_id,
        object_key,
        presigned_url,
    )
    return object_key, presigned_url, pdf_file_name


def _split_recipient(phone_number: str) -> tuple[str, str]:
    settings = get_settings()
    digits = "".join(ch for ch in phone_number if ch.isdigit())
    if not digits:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="Phone number is required.",
            error_code="INVALID_WHATSAPP_PHONE_NUMBER",
        )
    default_country_code = settings.whatsapp_default_country_code
    country_digits = "".join(ch for ch in default_country_code if ch.isdigit())
    if len(digits) == 10:
        return default_country_code, digits
    if country_digits and digits.startswith(country_digits) and len(
            digits) > len(country_digits):
        return f"+{country_digits}", digits[len(country_digits):]
    if len(digits) < 10 or len(digits) > 15:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="Phone number must contain between 10 and 15 digits.",
            error_code="INVALID_WHATSAPP_PHONE_NUMBER",
            details={"phone_number": phone_number},
        )
    return default_country_code, digits


def _build_whatsapp_template_payload(
    *,
    template_name: str,
    country_code: str,
    phone_number: str,
    body_values: list[str],
    invoice_pdf_url: str,
    invoice_pdf_file_name: str,
) -> dict:
    settings = get_settings()
    recipient_digits = f"{''.join(ch for ch in country_code if ch.isdigit())}{phone_number}"
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_digits,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": settings.whatsapp_template_language_code,
            },
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "document",
                            "document": {
                                "link": invoice_pdf_url,
                                "filename": invoice_pdf_file_name,
                            },
                        },
                    ],
                },
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": value,
                        }
                        for value in body_values
                    ],
                },
            ],
        },
    }


def _build_booking_invoice_proof_payload(
    *,
    country_code: str,
    phone_number: str,
    customer_name: str,
    booking_id: int,
    invoice_number: str,
    total_payable_amount: str,
    invoice_pdf_url: str,
    invoice_pdf_file_name: str,
) -> dict:
    settings = get_settings()
    return _build_whatsapp_template_payload(
        template_name=settings.whatsapp_template_name,
        country_code=country_code,
        phone_number=phone_number,
        body_values=[
            customer_name,
            str(booking_id),
            invoice_number,
            total_payable_amount,
        ],
        invoice_pdf_url=invoice_pdf_url,
        invoice_pdf_file_name=invoice_pdf_file_name,
    )


def _build_payment_reminder_payload(
    *,
    country_code: str,
    phone_number: str,
    customer_name: str,
    booking_id: int,
    invoice_number: str,
    total_payable_amount: str,
    total_paid_amount: str,
    total_remaining_amount: str,
    invoice_pdf_url: str,
    invoice_pdf_file_name: str,
) -> dict:
    settings = get_settings()
    template_name = (
        settings.whatsapp_payment_reminder_template_name
        or settings.whatsapp_template_name
    )
    return _build_whatsapp_template_payload(
        template_name=template_name,
        country_code=country_code,
        phone_number=phone_number,
        body_values=[
            customer_name,
            str(booking_id),
            invoice_number,
            total_payable_amount,
            total_paid_amount,
            total_remaining_amount,
        ],
        invoice_pdf_url=invoice_pdf_url,
        invoice_pdf_file_name=invoice_pdf_file_name,
    )


def _whatsapp_meta_messages_url() -> str:
    settings = get_settings()
    return (
        f"{settings.whatsapp_meta_base_url.rstrip('/')}/"
        f"{settings.whatsapp_meta_api_version}/"
        f"{settings.whatsapp_meta_phone_number_id}/messages"
    )


def _raise_whatsapp_meta_provider_error(details: dict) -> None:
    logger.warning("WhatsApp Meta API rejected message request: %s", details)
    raise AppError(
        status_code=status.HTTP_502_BAD_GATEWAY,
        message="WhatsApp Meta API rejected the message request.",
        error_code="WHATSAPP_META_PROVIDER_ERROR",
        details=details,
    )


def _send_whatsapp_meta_payload(payload: dict) -> dict:
    settings = get_settings()
    url = _whatsapp_meta_messages_url()
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.whatsapp_meta_access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "FranchiseBilling/1.0 (+https://crmapi.lifeweblink.com)",
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
        details["provider_status_code"] = exc.code
        _raise_whatsapp_meta_provider_error(details)
    except error.URLError as exc:
        raise AppError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            message="Failed to reach the WhatsApp Meta API provider.",
            error_code="WHATSAPP_META_PROVIDER_UNREACHABLE",
            details={"reason": str(exc.reason)},
        ) from exc

    try:
        response_payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            message="WhatsApp Meta API returned an invalid response.",
            error_code="WHATSAPP_META_PROVIDER_INVALID_RESPONSE",
            details={"raw_response": raw},
        ) from exc

    if not isinstance(response_payload, dict):
        raise AppError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            message="WhatsApp Meta API returned an invalid response.",
            error_code="WHATSAPP_META_PROVIDER_INVALID_RESPONSE",
            details={"raw_response": response_payload},
        )

    if response_payload.get("success") is False:
        _raise_whatsapp_meta_provider_error(response_payload)

    return response_payload


def _extract_whatsapp_provider_message_id(response_payload: dict) -> str | None:
    if isinstance(response_payload.get("id"), str):
        return response_payload["id"]

    messages = response_payload.get("messages")
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        message_id = messages[0].get("id")
        if isinstance(message_id, str):
            return message_id

    data = response_payload.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("id"), str):
            return data["id"]
        data_messages = data.get("messages")
        if isinstance(data_messages, list) and data_messages and isinstance(data_messages[0], dict):
            message_id = data_messages[0].get("id")
            if isinstance(message_id, str):
                return message_id

    return None


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
    provider_message_id = _extract_whatsapp_provider_message_id(response_payload)

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
            details={
                "booking_id": booking_id,
                "customer_id": customer_id
            },
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
    invoice_pdf: UploadFile,
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
            message=
            "Customer does not have a phone number for WhatsApp delivery.",
            error_code="CUSTOMER_WHATSAPP_NUMBER_MISSING",
            details={"customer_id": customer.id},
        )
    object_key, presigned_url, pdf_file_name = prepare_invoice_pdf_upload(
        booking_id=booking.id,
        invoice_number=invoice.invoice_number,
        invoice_pdf=invoice_pdf,
    )
    country_code, phone_number = _split_recipient(recipient_input)
    payload = _build_booking_invoice_proof_payload(
        country_code=country_code,
        phone_number=phone_number,
        customer_name=customer.full_name,
        booking_id=booking.id,
        invoice_number=invoice.invoice_number,
        total_payable_amount=str(invoice.total_payable_amount),
        invoice_pdf_url=presigned_url,
        invoice_pdf_file_name=pdf_file_name,
    )
    response_payload = _send_whatsapp_meta_payload(payload)
    text = (f"WhatsApp Meta invoice send for customer {customer.full_name}, "
            f"booking {booking.id}, invoice {invoice.invoice_number}.")
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
        action="notification.whatsapp_meta_proof_sent",
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
            "s3_object_key": object_key,
            "invoice_pdf_url": presigned_url,
            "recipient": f"{country_code}{phone_number}",
            "provider_message_id": notification.provider_message_id,
        },
    )
    notification.provider_response = {
        **(notification.provider_response or {}),
        "s3_object_key": object_key,
        "invoice_pdf_url": presigned_url,
    }
    return notification


def send_payment_reminder_whatsapp_for_actor(
    db: Session,
    *,
    actor: User,
    actor_role: UserRole,
    actor_franchise_id: int | None,
    customer_id: int,
    booking_id: int,
    invoice_pdf: UploadFile,
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

    total_remaining_amount = invoice.total_payable_amount - invoice.total_paid_amount
    if total_remaining_amount <= 0:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            message="Payment reminder is not applicable because payment is already complete.",
            error_code="PAYMENT_REMINDER_NOT_APPLICABLE",
            details={
                "booking_id": booking.id,
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "payment_status": invoice.payment_status.value,
            },
        )

    recipient_input = customer.whatsapp_number or customer.mobile_number
    if not recipient_input:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=
            "Customer does not have a phone number for WhatsApp delivery.",
            error_code="CUSTOMER_WHATSAPP_NUMBER_MISSING",
            details={"customer_id": customer.id},
        )
    object_key, presigned_url, pdf_file_name = prepare_invoice_pdf_upload(
        booking_id=booking.id,
        invoice_number=invoice.invoice_number,
        invoice_pdf=invoice_pdf,
    )
    country_code, phone_number = _split_recipient(recipient_input)
    payload = _build_payment_reminder_payload(
        country_code=country_code,
        phone_number=phone_number,
        customer_name=customer.full_name,
        booking_id=booking.id,
        invoice_number=invoice.invoice_number,
        total_payable_amount=str(invoice.total_payable_amount),
        total_paid_amount=str(invoice.total_paid_amount),
        total_remaining_amount=str(total_remaining_amount),
        invoice_pdf_url=presigned_url,
        invoice_pdf_file_name=pdf_file_name,
    )
    response_payload = _send_whatsapp_meta_payload(payload)
    text = (
        f"WhatsApp Meta payment reminder sent for customer {customer.full_name}, "
        f"booking {booking.id}, invoice {invoice.invoice_number}, pending {total_remaining_amount}."
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
        action="notification.whatsapp_meta_payment_reminder_sent",
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
            "total_payable_amount": str(invoice.total_payable_amount),
            "total_paid_amount": str(invoice.total_paid_amount),
            "total_remaining_amount": str(total_remaining_amount),
            "s3_object_key": object_key,
            "invoice_pdf_url": presigned_url,
            "recipient": f"{country_code}{phone_number}",
            "provider_message_id": notification.provider_message_id,
        },
    )
    notification.provider_response = {
        **(notification.provider_response or {}),
        "s3_object_key": object_key,
        "invoice_pdf_url": presigned_url,
    }
    return notification
