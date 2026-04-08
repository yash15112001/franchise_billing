from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from domains.payments.domain.enums import PaymentMode
from foundation.database.base import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    mode: Mapped[PaymentMode] = mapped_column(
        SqlEnum(
            PaymentMode,
            name="payment_mode",
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        index=True,
    )
    verified_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    reference_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
