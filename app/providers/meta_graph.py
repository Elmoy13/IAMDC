import httpx

from app.core.exceptions import MetaSendError
from app.core.logging import get_logger

logger = get_logger(__name__)

GRAPH_API_URL = "https://graph.facebook.com/v21.0/me/messages"


async def send_text_message(
    recipient_id: str,
    text: str,
    access_token: str,
) -> dict:
    """Send a text message to a user via Meta Graph API."""
    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE",
        "message": {"text": text},
    }
    params = {"access_token": access_token}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GRAPH_API_URL, json=payload, params=params)

    if response.status_code != 200:
        logger.error(
            "meta_graph_send_failed",
            status=response.status_code,
            body=response.text,
        )
        raise MetaSendError(detail=f"Graph API error {response.status_code}: {response.text}")

    return response.json()
