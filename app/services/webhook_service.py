import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ChannelNotFoundError
from app.core.logging import get_logger
from app.db.models import Channel, ChannelBrand, Contact, Conversation, Message

logger = get_logger(__name__)


@dataclass
class IncomingMessageResult:
    conversation_id: uuid.UUID
    message_text: str
    mode: str
    agency_id: uuid.UUID
    active_brand_id: uuid.UUID | None


def _resolve_active_brand(
    channel_brands: list[ChannelBrand],
    message_text: str,
) -> ChannelBrand:
    """Resolve which brand responds when there are multiple.

    Strategy:
    1. Single brand → that one
    2. Multiple with trigger_keywords → first match by priority
    3. No match → primary (is_primary=True)
    4. Fallback → lowest priority number
    """
    if len(channel_brands) == 1:
        return channel_brands[0]

    text_lower = message_text.lower()
    for cb in sorted(channel_brands, key=lambda x: x.priority):
        if cb.trigger_keywords:
            for keyword in cb.trigger_keywords:
                if keyword.lower() in text_lower:
                    return cb

    for cb in channel_brands:
        if cb.is_primary:
            return cb

    return sorted(channel_brands, key=lambda x: x.priority)[0]


async def _get_or_create_contact(
    db: AsyncSession,
    agency_id: uuid.UUID,
    platform: str,
    platform_user_id: str,
    name: str | None = None,
    page_access_token: str | None = None,
) -> Contact:
    """Find an existing contact or create a new one."""
    result = await db.execute(
        select(Contact).where(
            Contact.agency_id == agency_id,
            Contact.platform == platform,
            Contact.platform_user_id == platform_user_id,
        )
    )
    contacts = result.scalars().all()
    if len(contacts) == 1:
        return contacts[0]
    if len(contacts) > 1:
        # Duplicates exist — use the oldest and log a warning
        contact = min(contacts, key=lambda c: c.created_at or datetime.min)
        logger.warning(
            "duplicate_contacts_detected",
            count=len(contacts),
            agency_id=str(contact.agency_id),
            platform=contact.platform,
            platform_user_id=contact.platform_user_id,
            keeping_id=str(contact.id),
        )
        return contact

    contact = Contact(
        agency_id=agency_id,
        user_id=uuid.UUID(int=0),  # Legacy field; agency_id is the real owner
        platform=platform,
        platform_user_id=platform_user_id,
        name=name or platform_user_id,
    )
    db.add(contact)
    await db.flush()

    # Enrich new contact with profile picture from Graph API
    if page_access_token:
        try:
            from app.providers import meta_graph
            profile = await meta_graph.get_user_profile(
                platform_user_id=platform_user_id,
                page_access_token=page_access_token,
            )
            contact.name = profile.get("name") or contact.name
            contact.profile_picture_url = profile.get("profile_pic")
            await db.flush()
        except Exception as exc:
            logger.warning("contact_enrichment_failed", error=str(exc))

    return contact


async def _get_or_create_conversation(
    db: AsyncSession,
    agency_id: uuid.UUID,
    contact_id: uuid.UUID,
    channel_id: uuid.UUID,
    active_brand_id: uuid.UUID | None,
) -> Conversation:
    """Find an open conversation or create a new one."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.contact_id == contact_id,
            Conversation.channel_id == channel_id,
            Conversation.status == "open",
        )
    )
    convs = result.scalars().all()
    if len(convs) == 1:
        return convs[0]
    if len(convs) > 1:
        # Duplicates exist — keep the one with the most recent activity
        conversation = min(
            convs,
            key=lambda c: (c.last_message_at or datetime.min, str(c.id)),
        )
        logger.warning(
            "duplicate_conversations_detected",
            count=len(convs),
            contact_id=str(conversation.contact_id),
            channel_id=str(conversation.channel_id),
            keeping_id=str(conversation.id),
        )
        return conversation

    conversation = Conversation(
        agency_id=agency_id,
        user_id=uuid.UUID(int=0),  # Legacy field
        contact_id=contact_id,
        channel_id=channel_id,
        active_brand_id=active_brand_id,
        status="open",
        mode="ai",
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def process_incoming_message(
    db: AsyncSession,
    page_id: str,
    sender_id: str,
    message_text: str,
) -> IncomingMessageResult:
    """Process an incoming message from Meta.

    Returns IncomingMessageResult with conversation_id, message_text, mode,
    agency_id, and active_brand_id for downstream AI reply.
    """
    # 1. Find the channel by page_id, eagerly load brands
    result = await db.execute(
        select(Channel)
        .where(Channel.page_id == page_id)
        .options(selectinload(Channel.channel_brands))
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise ChannelNotFoundError(detail=f"No channel found for page_id={page_id}")

    # 2. Resolve active brand
    active_brand_id: uuid.UUID | None = None
    if channel.channel_brands:
        active_brand = _resolve_active_brand(channel.channel_brands, message_text)
        active_brand_id = active_brand.brand_id

    # 3. Get or create contact (pass token for profile enrichment)
    _page_token: str | None = None
    if channel.access_token:
        try:
            from app.services.channel_service import get_channel_access_token
            _page_token = await get_channel_access_token(db, channel.id)
        except Exception:
            _page_token = None

    contact = await _get_or_create_contact(
        db,
        agency_id=channel.agency_id,
        platform=channel.platform or "facebook",
        platform_user_id=sender_id,
        page_access_token=_page_token,
    )

    # 4. Get or create conversation
    conversation = await _get_or_create_conversation(
        db,
        agency_id=channel.agency_id,
        contact_id=contact.id,
        channel_id=channel.id,
        active_brand_id=active_brand_id,
    )

    # 5. Save the incoming message
    now = datetime.utcnow()
    incoming = Message(
        conversation_id=conversation.id,
        sender="customer",
        content=message_text,
        sent_at=now,
    )
    db.add(incoming)

    # 6. Update last_message_at
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation.id)
        .values(last_message_at=now)
    )

    await db.commit()

    logger.info(
        "incoming_message_saved",
        conversation_id=str(conversation.id),
        sender_id=sender_id,
        mode=conversation.mode,
        agency_id=str(channel.agency_id),
    )
    return IncomingMessageResult(
        conversation_id=conversation.id,
        message_text=message_text,
        mode=conversation.mode or "ai",
        agency_id=channel.agency_id,
        active_brand_id=active_brand_id,
    )
