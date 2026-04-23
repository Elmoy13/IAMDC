import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConversationNotFoundError
from app.core.logging import get_logger
from app.db.models import Conversation, Message
from app.providers import meta_graph
from app.services import ai_service
from app.services.channel_service import get_channel_access_token

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a helpful customer service assistant. "
    "Reply concisely and professionally in the same language the customer uses. "
    "If you don't know the answer, say so honestly."
)


async def handle_ai_reply(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    message_text: str,
) -> Message:
    """Generate an AI response and send it to the customer via Meta."""
    # 1. Load conversation with channel and contact
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise ConversationNotFoundError()

    # 2. Fetch last 10 messages for context
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sent_at.desc())
        .limit(10)
    )
    recent_messages = list(reversed(msg_result.scalars().all()))

    history = [
        {"role": m.sender, "content": m.content}
        for m in recent_messages
        if m.content
    ]

    # 3. Call AI provider
    ai_response = await ai_service.generate_response(
        system_prompt=SYSTEM_PROMPT,
        user_message=message_text,
        history=history,
    )

    # 4. Send to customer via Meta Graph API
    access_token = await get_channel_access_token(db, conversation.channel.id)
    await meta_graph.send_text_message(
        recipient_id=conversation.contact.platform_user_id,
        text=ai_response,
        access_token=access_token,
    )

    # 5. Save AI message in DB
    now = datetime.now(timezone.utc)
    ai_message = Message(
        conversation_id=conversation_id,
        sender="ai",
        content=ai_response,
        sent_at=now,
    )
    db.add(ai_message)

    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(last_message_at=now)
    )

    await db.commit()
    await db.refresh(ai_message)

    logger.info("ai_reply_sent", conversation_id=str(conversation_id))
    return ai_message


async def send_manual_message(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    message_text: str,
) -> Message:
    """Send a manual agent message to the customer via Meta."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise ConversationNotFoundError()

    # Send via Meta Graph API
    access_token = await get_channel_access_token(db, conversation.channel.id)
    await meta_graph.send_text_message(
        recipient_id=conversation.contact.platform_user_id,
        text=message_text,
        access_token=access_token,
    )

    # Save in DB
    now = datetime.now(timezone.utc)
    agent_message = Message(
        conversation_id=conversation_id,
        sender="agent",
        content=message_text,
        sent_at=now,
    )
    db.add(agent_message)

    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(last_message_at=now)
    )

    await db.commit()
    await db.refresh(agent_message)

    logger.info("manual_message_sent", conversation_id=str(conversation_id))
    return agent_message
