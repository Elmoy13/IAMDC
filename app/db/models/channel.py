import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Text, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.brand import Brand
    from app.db.models.conversation import Conversation


class Channel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("brand_id", "platform", "page_id", name="channels_brand_platform_page_unique"),
    )

    agency_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    phone_number_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="channel")
    brand: Mapped["Brand"] = relationship(back_populates="channels", lazy="selectin")
