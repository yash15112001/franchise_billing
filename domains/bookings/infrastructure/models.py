from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domains.bookings.domain.enums import BookingServiceStatus
from foundation.database.base import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_id: Mapped[int] = mapped_column(ForeignKey("franchises.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    service_status: Mapped[BookingServiceStatus] = mapped_column(
        SqlEnum(
            BookingServiceStatus,
            name="booking_service_status",
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=BookingServiceStatus.PENDING,
        server_default=BookingServiceStatus.PENDING.value,
        index=True,
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    items: Mapped[list["BookingItem"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
    )


class BookingItem(Base):
    __tablename__ = "booking_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    booking: Mapped[Booking] = relationship(back_populates="items")
