from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from foundation.database.base import Base


class DailySettlement(Base):
    __tablename__ = "daily_settlements"
    __table_args__ = (UniqueConstraint("franchise_id",
                                       "business_date",
                                       name="uq_franchise_settlement"), )

    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_id: Mapped[int] = mapped_column(ForeignKey("franchises.id"),
                                              index=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    total_income: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    pending_income: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cash_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    upi_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    card_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    bank_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String(20), default="settled")
    closed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"),
                                                   index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
