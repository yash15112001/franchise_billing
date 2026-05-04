from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from foundation.database.base import Base


class NotificationChannel(StrEnum):
    WHATSAPP = "whatsapp"


class NotificationMessageType(StrEnum):
    TEXT = "text"
    DOCUMENT = "document"


class NotificationDeliveryStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"


class OutboundNotification(Base):
    __tablename__ = "outbound_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_id: Mapped[int | None] = mapped_column(
        ForeignKey("franchises.id"),
        nullable=True,
        index=True,
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"),
        nullable=True,
        index=True,
    )
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id"),
        nullable=True,
        index=True,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        SqlEnum(
            NotificationChannel,
            name="notification_channel",
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        index=True,
    )
    message_type: Mapped[NotificationMessageType] = mapped_column(
        SqlEnum(
            NotificationMessageType,
            name="notification_message_type",
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        index=True,
    )
    delivery_status: Mapped[NotificationDeliveryStatus] = mapped_column(
        SqlEnum(
            NotificationDeliveryStatus,
            name="notification_delivery_status",
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        index=True,
    )
    recipient: Mapped[str] = mapped_column(String(32), index=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
