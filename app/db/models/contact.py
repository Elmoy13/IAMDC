import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.conversation import Conversation


class Contact(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "contacts"

    agency_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_picture_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=True
    )

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="contact")
