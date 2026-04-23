import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, DateTime, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel


class ChannelBrand(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "channel_brands"
    __table_args__ = (
        UniqueConstraint("channel_id", "brand_id", name="uix_channel_brand"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    priority: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    trigger_keywords: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )

    channel: Mapped["Channel"] = relationship(back_populates="channel_brands")
