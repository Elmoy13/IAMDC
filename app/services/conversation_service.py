"""Service layer for conversation UX endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConversationNotFoundError
from app.core.logging import get_logger
from app.db.models.channel import Channel
from app.db.models.channel_brand import ChannelBrand
from app.db.models.contact import Contact
from app.db.models.conversation import Conversation
from app.db.models.message import Message

logger = get_logger(__name__)


def _build_active_brand(conv) -> dict | None:
    """Build active_brand dict from conversation's active_brand_id."""
    if not conv.active_brand_id:
        return None
    return {"id": conv.active_brand_id, "name": str(conv.active_brand_id)}


async def list_conversations_by_agency(
    db: AsyncSession,
    agency_id: uuid.UUID,
    status: str = "open",
    brand_id: Optional[uuid.UUID] = None,
    channel_id: Optional[uuid.UUID] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List conversations with summary (last message, unread, contact, channel)."""
    query = (
        select(Conversation)
        .where(
            Conversation.agency_id == agency_id,
            Conversation.status == status,
        )
        .order_by(Conversation.last_message_at.desc().nullslast())
        .limit(limit)
        .offset(offset)
    )

    if brand_id is not None:
        query = query.where(Conversation.active_brand_id == brand_id)
    if channel_id is not None:
        query = query.where(Conversation.channel_id == channel_id)

    result = await db.execute(query)
    conversations = result.scalars().all()

    items: list[dict] = []
    for conv in conversations:
        # Last message
        last_msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.sent_at.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()

        # Unread count: customer messages after last_read_at
        last_read = conv.last_read_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
        unread_q = select(func.count()).select_from(Message).where(
            Message.conversation_id == conv.id,
            Message.sender == "customer",
            Message.sent_at > last_read,
        )
        unread_result = await db.execute(unread_q)
        unread_count = unread_result.scalar() or 0

        contact = conv.contact
        channel = conv.channel

        items.append({
            "id": conv.id,
            "status": conv.status or "open",
            "mode": conv.mode or "ai",
            "last_message_at": conv.last_message_at,
            "last_message_preview": (last_msg.content[:100] if last_msg and last_msg.content else None),
            "last_message_sender": last_msg.sender if last_msg else None,
            "unread_count": unread_count,
            "contact": {
                "id": contact.id,
                "platform": contact.platform or "",
                "platform_user_id": contact.platform_user_id or "",
                "name": contact.name,
                "profile_picture_url": contact.profile_picture_url,
            },
            "channel": {
                "id": channel.id,
                "platform": channel.platform or "",
                "page_id": channel.page_id,
                "page_name": None,
            },
            "active_brand": _build_active_brand(conv),
            "tags": conv.tags if conv.tags else [],
        })

    return items


async def get_conversation_with_messages(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    agency_id: uuid.UUID,
    limit: int = 50,
    before: Optional[datetime] = None,
) -> Optional[dict]:
    """Return conversation with its messages and metadata."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        return None
    if str(conversation.agency_id) != str(agency_id):
        return None

    # Messages query
    msg_query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
    )
    if before is not None:
        msg_query = msg_query.where(Message.sent_at < before)
    msg_query = msg_query.order_by(Message.sent_at.asc()).limit(limit)

    msg_result = await db.execute(msg_query)
    messages = msg_result.scalars().all()

    # Total message count
    total_result = await db.execute(
        select(func.count()).select_from(Message).where(
            Message.conversation_id == conversation_id
        )
    )
    total_messages = total_result.scalar() or 0

    # Mark as read
    conversation.last_read_at = datetime.now(timezone.utc)
    await db.commit()

    contact = conversation.contact
    channel = conversation.channel

    return {
        "id": conversation.id,
        "status": conversation.status or "open",
        "mode": conversation.mode or "ai",
        "contact": {
            "id": contact.id,
            "platform": contact.platform or "",
            "platform_user_id": contact.platform_user_id or "",
            "name": contact.name,
            "profile_picture_url": contact.profile_picture_url,
        },
        "channel": {
            "id": channel.id,
            "platform": channel.platform or "",
            "page_id": channel.page_id,
            "page_name": None,
        },
        "active_brand": _build_active_brand(conversation),
        "messages": [
            {
                "id": m.id,
                "conversation_id": m.conversation_id,
                "sender": m.sender or "customer",
                "content": m.content or "",
                "sent_at": m.sent_at,
                "ai_suggestion": m.ai_suggestion,
            }
            for m in messages
        ],
        "total_messages": total_messages,
    }


async def send_agent_message(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    agency_id: uuid.UUID,
    content: str,
    switch_to_manual: bool = True,
) -> Message:
    """Send a message as a human agent.

    1. Validates conversation exists and belongs to the agency
    2. Gets channel + access token
    3. Sends via Meta Graph API
    4. Saves the message in DB
    5. If switch_to_manual, updates conversation.mode
    """
    from app.providers import meta_graph
    from app.services.channel_service import get_channel_access_token

    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise ConversationNotFoundError()
    if str(conversation.agency_id) != str(agency_id):
        raise ConversationNotFoundError(detail="No access to this conversation")

    # Send via platform
    access_token = await get_channel_access_token(db, conversation.channel_id)
    contact = conversation.contact
    await meta_graph.send_text_message(
        recipient_id=contact.platform_user_id,
        text=content,
        access_token=access_token,
    )

    # Save message
    now = datetime.now(timezone.utc)
    agent_message = Message(
        conversation_id=conversation_id,
        sender="agent",
        content=content,
        sent_at=now,
    )
    db.add(agent_message)

    # Update conversation
    update_values: dict = {"last_message_at": now}
    if switch_to_manual:
        update_values["mode"] = "manual"
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(**update_values)
    )

    await db.commit()
    await db.refresh(agent_message)

    logger.info(
        "agent_message_sent",
        conversation_id=str(conversation_id),
        switch_to_manual=switch_to_manual,
    )
    return agent_message
