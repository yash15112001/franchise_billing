from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from foundation.database.base import Base


class CustomerType(StrEnum):
    NEW = "new"
    REGULAR = "regular"
    VIP = "vip"


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("franchise_id",
                                       "mobile_number",
                                       name="uq_customer_mobile"), )

    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_id: Mapped[int] = mapped_column(ForeignKey("franchises.id"),
                                              index=True)
    full_name: Mapped[str] = mapped_column(String(120), index=True)
    mobile_number: Mapped[str] = mapped_column(String(10), index=True)
    whatsapp_number: Mapped[str] = mapped_column(String(10),
                                                 default="",
                                                 server_default="")
    type: Mapped[CustomerType] = mapped_column(
        SqlEnum(
            CustomerType,
            name="customer_type",
            native_enum=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        default=CustomerType.NEW,
        server_default=CustomerType.NEW.value,
        index=True,
    )
    email: Mapped[str | None] = mapped_column(String(320),
                                              nullable=True,
                                              index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="customer")


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (UniqueConstraint(
        "customer_id",
        "registration_number",
        name="uq_vehicle_customer_registration",
    ), )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"),
                                             index=True)
    franchise_id: Mapped[int] = mapped_column(ForeignKey("franchises.id"),
                                              index=True)
    name: Mapped[str | None] = mapped_column(String(120),
                                             nullable=True,
                                             index=True)
    registration_number: Mapped[str] = mapped_column(String(32), index=True)
    color: Mapped[str] = mapped_column(String(80),
                                       default="",
                                       server_default="")
    model: Mapped[str] = mapped_column(String(50),
                                       default="",
                                       server_default="")
    vehicle_type: Mapped[str] = mapped_column(
        String(50),
        default="",
        server_default="",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    customer: Mapped[Customer] = relationship(back_populates="vehicles")
