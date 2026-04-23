"""Channel access token management with encryption."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.exceptions import ChannelNotFoundError
from app.db.models import Channel


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
