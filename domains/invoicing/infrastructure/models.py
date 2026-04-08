from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from domains.invoicing.domain.enums import InvoicePaymentStatus
from foundation.database.base import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    franchise_id: Mapped[int] = mapped_column(ForeignKey("franchises.id"), index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    gst_included: Mapped[bool] = mapped_column(Boolean, default=True)
    gst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_payable_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    payment_status: Mapped[InvoicePaymentStatus] = mapped_column(
        SqlEnum(
            InvoicePaymentStatus,
            name="invoice_payment_status",
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=InvoicePaymentStatus.PENDING,
        server_default=InvoicePaymentStatus.PENDING.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
