from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from domains.bookings.infrastructure.models import Booking
from domains.invoicing.infrastructure.models import Invoice
from domains.payments.domain.enums import PaymentMode
from domains.payments.infrastructure.models import Payment


def get_daily_dashboard(db: Session, *, franchise_id: int, business_date: date) -> dict:
    booking_row = db.execute(
        select(
            func.coalesce(func.count(Booking.id), 0),
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.id.isnot(None), Invoice.total_payable_amount),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .select_from(Booking)
        .outerjoin(Invoice, Invoice.booking_id == Booking.id)
        .where(
            func.date(Booking.created_at) == business_date,
            Booking.franchise_id == franchise_id,
        )
    ).one()

    outstanding_row = db.execute(
        select(
            func.coalesce(
                func.count(
                    case(
                        (
                            (Invoice.id.is_(None))
                            | (
                                Invoice.total_payable_amount
                                > Invoice.total_paid_amount
                            ),
                            Booking.id,
                        ),
                        else_=None,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Invoice.id.isnot(None),
                            Invoice.total_payable_amount - Invoice.total_paid_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.id.is_(None), Decimal("0.00")),
                        (
                            Invoice.total_payable_amount > Invoice.total_paid_amount,
                            Invoice.total_payable_amount - Invoice.total_paid_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.count(case((Invoice.id.isnot(None), Booking.id), else_=None)),
                0,
            ),
        )
        .select_from(Booking)
        .outerjoin(Invoice, Invoice.booking_id == Booking.id)
        .where(Booking.franchise_id == franchise_id)
    ).one()

    payment_row = db.execute(
        select(
            func.coalesce(
                func.sum(
                    case((Payment.mode == PaymentMode.CASH, Payment.amount), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((Payment.mode == PaymentMode.UPI, Payment.amount), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((Payment.mode == PaymentMode.CARD, Payment.amount), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (Payment.mode == PaymentMode.BANK_TRANSFER, Payment.amount),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .select_from(Payment)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .where(
            func.date(Payment.created_at) == business_date,
            Invoice.franchise_id == franchise_id,
        )
    ).one()

    registered_services, registered_revenue = booking_row
    payment_pending_services, invoice_pending_amount, pending_income, services_with_payment = outstanding_row
    cash_income, upi_income, card_income, bank_income = payment_row
    total_income = (
        Decimal(cash_income)
        + Decimal(upi_income)
        + Decimal(card_income)
        + Decimal(bank_income)
    )
    return {
        "business_date": business_date,
        "registered_services": int(registered_services),
        "registered_revenue": Decimal(registered_revenue),
        "services_with_payment": int(services_with_payment),
        "payment_pending_services": int(payment_pending_services),
        "total_income": total_income,
        "pending_income": Decimal(pending_income),
        "invoice_pending_amount": Decimal(invoice_pending_amount),
        "cash_income": Decimal(cash_income),
        "upi_income": Decimal(upi_income),
        "card_income": Decimal(card_income),
        "bank_income": Decimal(bank_income),
    }


def get_monthly_summary(db: Session, *, franchise_id: int, year: int, month: int) -> dict:
    booking_row = db.execute(
        select(
            func.coalesce(func.count(Booking.id), 0),
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.id.isnot(None), Invoice.total_payable_amount),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .select_from(Booking)
        .outerjoin(Invoice, Invoice.booking_id == Booking.id)
        .where(
            Booking.franchise_id == franchise_id,
            func.extract("year", Booking.created_at) == year,
            func.extract("month", Booking.created_at) == month,
        )
    ).one()

    payment_row = db.execute(
        select(
            func.coalesce(func.sum(Payment.amount), 0),
            func.coalesce(
                func.sum(
                    case((Payment.mode == PaymentMode.CASH, Payment.amount), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((Payment.mode == PaymentMode.UPI, Payment.amount), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((Payment.mode == PaymentMode.CARD, Payment.amount), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (Payment.mode == PaymentMode.BANK_TRANSFER, Payment.amount),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .select_from(Payment)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .where(
            Invoice.franchise_id == franchise_id,
            func.extract("year", Payment.created_at) == year,
            func.extract("month", Payment.created_at) == month,
        )
    ).one()

    pending_income = db.scalar(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.id.is_(None), Decimal("0.00")),
                        (
                            Invoice.total_payable_amount > Invoice.total_paid_amount,
                            Invoice.total_payable_amount - Invoice.total_paid_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            )
        )
        .select_from(Booking)
        .outerjoin(Invoice, Invoice.booking_id == Booking.id)
        .where(Booking.franchise_id == franchise_id)
    )

    booking_count, booked_revenue = booking_row
    total_income, cash_income, upi_income, card_income, bank_income = payment_row
    return {
        "year": year,
        "month": month,
        "booking_count": int(booking_count),
        "booked_revenue": Decimal(booked_revenue),
        "total_income": Decimal(total_income),
        "pending_income": Decimal(pending_income or 0),
        "cash_income": Decimal(cash_income),
        "upi_income": Decimal(upi_income),
        "card_income": Decimal(card_income),
        "bank_income": Decimal(bank_income),
    }


def list_pending_payment_rows(db: Session, *, franchise_id: int) -> list[dict]:
    rows = db.execute(
        select(
            Booking.id,
            Booking.customer_id,
            Booking.vehicle_id,
            Invoice.id,
            func.coalesce(Invoice.total_payable_amount, Decimal("0")),
            func.coalesce(Invoice.total_paid_amount, Decimal("0")),
        )
        .select_from(Booking)
        .outerjoin(Invoice, Invoice.booking_id == Booking.id)
        .where(
            Booking.franchise_id == franchise_id,
            (Invoice.id.is_(None))
            | (Invoice.total_payable_amount > Invoice.total_paid_amount),
        )
        .order_by(Booking.created_at.desc())
    ).all()
    return [
        {
            "booking_id": booking_id,
            "customer_id": customer_id,
            "vehicle_id": vehicle_id,
            "invoice_id": invoice_id,
            "total_payable_amount": Decimal(total_payable),
            "total_paid_amount": Decimal(total_paid),
            "pending_amount": Decimal(total_payable) - Decimal(total_paid),
        }
        for booking_id, customer_id, vehicle_id, invoice_id, total_payable, total_paid in rows
    ]
