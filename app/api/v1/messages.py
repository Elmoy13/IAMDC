from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DbSession
from app.middleware.auth import get_user_agency
from app.schemas.message import AIReplyRequest, MessageResponse, SendMessageRequest
from app.services import message_service
from app.db.models import Conversation
from sqlalchemy import select

router = APIRouter(prefix="/messages", tags=["messages"])


async def _verify_agency_access(
    db: DbSession, conversation_id, agency: dict
) -> None:
    """Verify the conversation belongs to the user's agency."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if str(conv.agency_id) != str(agency["agency_id"]):
        raise HTTPException(status_code=403, detail="No access to this conversation")


@router.post("/ai-reply", response_model=MessageResponse)
async def ai_reply(
    payload: AIReplyRequest,
    db: DbSession,
    agency: dict = Depends(get_user_agency),
) -> MessageResponse:
    """Generate an AI response and send it to the customer."""
    await _verify_agency_access(db, payload.conversation_id, agency)
    msg = await message_service.handle_ai_reply(
        db=db,
        conversation_id=payload.conversation_id,
        message_text=payload.message_text,
    )
    return msg  # type: ignore[return-value]


@router.post("/send", response_model=MessageResponse)
async def send_message(
    payload: SendMessageRequest,
    db: DbSession,
    agency: dict = Depends(get_user_agency),
) -> MessageResponse:
    """Send a manual agent message to the customer."""
    await _verify_agency_access(db, payload.conversation_id, agency)
    msg = await message_service.send_manual_message(
        db=db,
        conversation_id=payload.conversation_id,
        message_text=payload.message_text,
    )
    return msg  # type: ignore[return-value]
