import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel


class Brand(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "brands"

    agency_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )

    channels: Mapped[list["Channel"]] = relationship(back_populates="brand")
