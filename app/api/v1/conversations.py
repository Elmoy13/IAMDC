import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import DbSession
from app.core.exceptions import ConversationNotFoundError
from app.db.models import Conversation, Message
from app.middleware.auth import get_current_user, get_user_agency
from app.schemas.conversation import (
    ConversationDetail,
    ConversationListItem,
    ConversationModeResponse,
    ConversationModeUpdate,
    MessageItem,
    SendMessageRequest,
)
from app.services import conversation_service
from sqlalchemy import select, update

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/by-agency/{agency_id}", response_model=list[ConversationListItem])
async def list_conversations(
    agency_id: uuid.UUID,
    db: DbSession,
    user: dict = Depends(get_current_user),
    agency: dict = Depends(get_user_agency),
    status: str = Query("open"),
    brand_id: Optional[uuid.UUID] = Query(None),
    channel_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List conversations for an agency with summary info."""
    if str(agency["agency_id"]) != str(agency_id):
        raise HTTPException(403, "No access to this agency")
    return await conversation_service.list_conversations_by_agency(
        db, agency_id, status=status, brand_id=brand_id,
        channel_id=channel_id, limit=limit, offset=offset,
    )


@router.get("/{conversation_id}/messages", response_model=ConversationDetail)
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    db: DbSession,
    agency: dict = Depends(get_user_agency),
    limit: int = Query(50, ge=1, le=200),
    before: Optional[datetime] = Query(None),
):
    """Get all messages for a conversation (chronological). Marks as read."""
    agency_id = uuid.UUID(str(agency["agency_id"]))
    result = await conversation_service.get_conversation_with_messages(
        db, conversation_id, agency_id, limit=limit, before=before,
    )
    if not result:
        raise ConversationNotFoundError()
    return result


@router.post("/{conversation_id}/send", response_model=MessageItem)
async def send_agent_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    db: DbSession,
    agency: dict = Depends(get_user_agency),
):
    """Send a message as a human agent."""
    agency_id = uuid.UUID(str(agency["agency_id"]))
    msg = await conversation_service.send_agent_message(
        db, conversation_id, agency_id,
        content=payload.content,
        switch_to_manual=payload.switch_to_manual,
    )
    return msg


@router.patch("/{conversation_id}/mode", response_model=ConversationModeResponse)
async def update_conversation_mode(
    conversation_id: uuid.UUID,
    payload: ConversationModeUpdate,
    db: DbSession,
    agency: dict = Depends(get_user_agency),
) -> ConversationModeResponse:
    """Toggle conversation mode between 'ai' and 'manual'.

    - mode='ai': incoming messages trigger automatic AI replies.
    - mode='manual': AI is disabled, only human agents can reply.
    """
    if payload.mode not in ("ai", "manual"):
        raise HTTPException(422, "mode must be 'ai' or 'manual'")

    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise ConversationNotFoundError()

    if str(conversation.agency_id) != str(agency["agency_id"]):
        raise HTTPException(status_code=403, detail="No access to this conversation")

    old_mode = conversation.mode
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(mode=payload.mode)
    )
    await db.commit()

    # If switching from manual to ai, generate an AI reply to the last customer message
    if old_mode == "manual" and payload.mode == "ai":
        last_customer_msg = await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.sender == "customer",
            )
            .order_by(Message.sent_at.desc())
            .limit(1)
        )
        last_msg = last_customer_msg.scalar_one_or_none()
        if last_msg and last_msg.content:
            try:
                from app.services.message_service import handle_ai_reply
                await handle_ai_reply(db, conversation_id, last_msg.content)
            except Exception:
                pass  # Best-effort: don't fail the mode toggle

    conversation.mode = payload.mode
    return conversation  # type: ignore[return-value]
