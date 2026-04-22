from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, Text, Time, func, text
from sqlalchemy.orm import Mapped, mapped_column

from foundation.database.base import Base


class Service(Base):
    """Vehicle service offered by franchises (wash, detailing, etc.)."""

    __tablename__ = "services"
    __table_args__ = (
        Index(
            "uq_services_active_name_vehicle_category",
            "name",
            "vehicle_type",
            "service_category",
            unique=True,
            postgresql_where=text("is_active IS TRUE"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    vehicle_type: Mapped[str] = mapped_column(String(50), index=True)
    service_category: Mapped[str] = mapped_column(String(60), index=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    estimated_duration: Mapped[time] = mapped_column(Time(timezone=False))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
