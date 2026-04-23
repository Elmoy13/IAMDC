import asyncio

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response

from app.api.deps import DbSession
from app.config import settings
from app.core.exceptions import WebhookVerificationError
from app.core.logging import get_logger
from app.core.security import verify_meta_signature
from app.db.session import async_session_factory
from app.schemas.webhook import MetaWebhookBody
from app.services import message_service, webhook_service

logger = get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.get("/meta")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
) -> Response:
    """Meta webhook verification endpoint."""
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        logger.info("webhook_verified")
        return Response(content=hub_challenge, media_type="text/plain")
    raise WebhookVerificationError()


async def _process_ai_reply(conversation_id, message_text: str) -> None:
    """Background task: generate AI reply and send it."""
    async with async_session_factory() as db:
        try:
            await message_service.handle_ai_reply(db, conversation_id, message_text)
        except Exception:
            logger.exception("background_ai_reply_failed", conversation_id=str(conversation_id))


@router.post("/meta", status_code=200)
async def receive_webhook(
    request: Request,
    body: MetaWebhookBody,
    db: DbSession,
    background_tasks: BackgroundTasks,
) -> dict:
    """Receive incoming messages from Meta.

    Returns 200 immediately; AI reply is processed in the background.
    """
    # Verify signature
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if signature and not verify_meta_signature(raw_body, signature):
        raise WebhookVerificationError(detail="Invalid signature")

    # Process each entry
    for entry in body.entry:
        for messaging in entry.messaging:
            if not messaging.message or not messaging.message.text:
                continue

            page_id = messaging.recipient.id
            sender_id = messaging.sender.id
            text = messaging.message.text

            # Save incoming message & get conversation
            result = await webhook_service.process_incoming_message(
                db=db,
                page_id=page_id,
                sender_id=sender_id,
                message_text=text,
            )

            # Fire-and-forget AI reply only if mode is not 'manual'
            if result.mode != "manual":
                background_tasks.add_task(_process_ai_reply, result.conversation_id, result.message_text)
            else:
                logger.info("ai_skipped_manual_mode", conversation_id=str(result.conversation_id))

    return {"status": "ok"}
