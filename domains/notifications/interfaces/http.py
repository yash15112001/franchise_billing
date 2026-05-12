from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session
from starlette import status

from domains.notifications.application.service import (
    send_booking_invoice_whatsapp_proof_for_actor,
    send_payment_reminder_whatsapp_for_actor,
)
from domains.users.domain.access import SEND_NOTIFICATIONS
from foundation.database.session import get_db
from foundation.errors import AppError
from foundation.web.dependencies import UserContext, require_permissions
from foundation.web.responses import error_response, internal_error_response, success_response

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/whatsapp/invoices")
def send_whatsapp_text_message(
        customer_id: int = Form(...),
        booking_id: int = Form(...),
        invoice_pdf: UploadFile = File(...),
        context: UserContext = Depends(
            require_permissions(SEND_NOTIFICATIONS)),
        db: Session = Depends(get_db),
) -> dict:
    try:
        notification = send_booking_invoice_whatsapp_proof_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            customer_id=customer_id,
            booking_id=booking_id,
            invoice_pdf=invoice_pdf,
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
            message="WhatsApp proof message sent successfully.",
            data={
                "notification_id": notification.id,
                "channel": notification.channel.value,
                "message_type": notification.message_type.value,
                "recipient": notification.recipient,
                "provider_message_id": notification.provider_message_id,
                "delivery_status": notification.delivery_status.value,
                "invoice_id": notification.invoice_id,
                "customer_id": notification.customer_id,
            },
            status_code=status.HTTP_201_CREATED,
        )


@router.post("/whatsapp/payment-reminders")
def send_whatsapp_payment_reminder(
        customer_id: int = Form(...),
        booking_id: int = Form(...),
        invoice_pdf: UploadFile = File(...),
        context: UserContext = Depends(
            require_permissions(SEND_NOTIFICATIONS)),
        db: Session = Depends(get_db),
) -> dict:
    try:
        notification = send_payment_reminder_whatsapp_for_actor(
            db,
            actor=context.user,
            actor_role=context.role,
            actor_franchise_id=context.franchise_id,
            customer_id=customer_id,
            booking_id=booking_id,
            invoice_pdf=invoice_pdf,
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
            message="WhatsApp payment reminder sent successfully.",
            data={
                "notification_id": notification.id,
                "channel": notification.channel.value,
                "message_type": notification.message_type.value,
                "recipient": notification.recipient,
                "provider_message_id": notification.provider_message_id,
                "delivery_status": notification.delivery_status.value,
                "invoice_id": notification.invoice_id,
                "customer_id": notification.customer_id,
            },
            status_code=status.HTTP_201_CREATED,
        )
