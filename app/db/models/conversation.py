import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel
    from app.db.models.contact import Contact
    from app.db.models.message import Message


class Conversation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "conversations"

    agency_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id"), nullable=False)
    active_brand_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    status: Mapped[str | None] = mapped_column(Text, default="open", nullable=True)
    mode: Mapped[str | None] = mapped_column(Text, default="ai", nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags: Mapped[Any | None] = mapped_column(JSON, nullable=True, default=list)

    contact: Mapped["Contact"] = relationship(back_populates="conversations", lazy="selectin")
    channel: Mapped["Channel"] = relationship(back_populates="conversations", lazy="selectin")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.sent_at")
