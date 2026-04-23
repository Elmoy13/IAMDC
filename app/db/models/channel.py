import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.channel_brand import ChannelBrand
    from app.db.models.conversation import Conversation


class Channel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "channels"

    agency_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    phone_number_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=True
    )

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="channel")
    channel_brands: Mapped[list["ChannelBrand"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
