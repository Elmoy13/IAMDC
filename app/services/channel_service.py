"""Channel access token management with encryption."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.exceptions import ChannelNotFoundError
from app.core.logging import get_logger
from app.db.models import Channel, ChannelBrand

logger = get_logger(__name__)


async def get_channel_access_token(db: AsyncSession, channel_id: uuid.UUID) -> str:
    """Get the decrypted access_token for a channel."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel or not channel.access_token:
        raise ChannelNotFoundError(detail=f"Channel {channel_id} has no access token")

    if channel.access_token_encrypted and settings.encryption_key:
        return decrypt_secret(channel.access_token)
    return channel.access_token


async def set_channel_access_token(
    db: AsyncSession,
    channel: Channel,
    new_token: str,
) -> None:
    """Set the access_token, encrypting it if encryption_key is configured."""
    if settings.encryption_key:
        channel.access_token = encrypt_secret(new_token)
        channel.access_token_encrypted = True
    else:
        channel.access_token = new_token
        channel.access_token_encrypted = False
    await db.flush()


async def create_channel_with_encrypted_token(
    db: AsyncSession,
    agency_id: uuid.UUID,
    user_id: uuid.UUID,
    platform: str,
    page_id: str,
    page_name: str,
    page_access_token: str,
    brand_id: uuid.UUID,
    is_primary: bool = True,
) -> Channel:
    """Create a channel with an encrypted token and link it to a brand.

    Idempotent: if a channel already exists for the same ``page_id`` in the
    agency, its token is refreshed and the existing row is returned.
    """
    result = await db.execute(
        select(Channel).where(
            Channel.agency_id == agency_id,
            Channel.platform == platform,
            Channel.page_id == page_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.access_token = encrypt_secret(page_access_token)
        existing.access_token_encrypted = True
        await db.commit()
        await db.refresh(existing)
        return existing

    channel = Channel(
        agency_id=agency_id,
        user_id=user_id,
        platform=platform,
        page_id=page_id,
        access_token=encrypt_secret(page_access_token),
        access_token_encrypted=True,
    )
    db.add(channel)
    await db.flush()

    channel_brand = ChannelBrand(
        channel_id=channel.id,
        brand_id=brand_id,
        is_primary=is_primary,
        priority=1,
    )
    db.add(channel_brand)
    await db.commit()
    await db.refresh(channel)

    return channel


async def list_channels_by_agency(
    db: AsyncSession,
    agency_id: uuid.UUID,
) -> list[dict]:
    """List channels for an agency with their associated brands."""
    result = await db.execute(
        select(Channel)
        .where(Channel.agency_id == agency_id)
        .options(selectinload(Channel.channel_brands))
    )
    channels = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "platform": c.platform,
            "page_id": c.page_id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "brands": [
                {"brand_id": str(cb.brand_id), "is_primary": cb.is_primary}
                for cb in c.channel_brands
            ],
        }
        for c in channels
    ]


async def delete_channel(
    db: AsyncSession,
    channel_id: uuid.UUID,
    agency_id: uuid.UUID,
) -> None:
    """Delete a channel. Attempts to unsubscribe from Meta webhook first."""
    result = await db.execute(
        select(Channel).where(
            Channel.id == channel_id,
            Channel.agency_id == agency_id,
        )
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise ChannelNotFoundError(
            detail=f"Channel {channel_id} not found in agency {agency_id}"
        )

    if channel.page_id and channel.access_token:
        from app.services.meta_oauth import unsubscribe_page_from_webhook

        try:
            token = await get_channel_access_token(db, channel.id)
            await unsubscribe_page_from_webhook(
                page_id=channel.page_id,
                page_access_token=token,
            )
        except Exception as exc:
            logger.warning(
                "unsubscribe_failed",
                channel_id=str(channel.id),
                error=str(exc),
            )

    await db.delete(channel)
    await db.commit()
