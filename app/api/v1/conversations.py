import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DbSession
from app.core.exceptions import ConversationNotFoundError
from app.db.models import Conversation
from app.middleware.auth import get_user_agency
from app.schemas.conversation import ConversationModeResponse, ConversationModeUpdate
from sqlalchemy import select, update

router = APIRouter(prefix="/conversations", tags=["conversations"])


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
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise ConversationNotFoundError()

    if str(conversation.agency_id) != str(agency["agency_id"]):
        raise HTTPException(status_code=403, detail="No access to this conversation")

    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(mode=payload.mode)
    )
    await db.commit()

    conversation.mode = payload.mode
    return conversation  # type: ignore[return-value]
