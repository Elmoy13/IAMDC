import httpx

from app.core.exceptions import MetaSendError
from app.core.logging import get_logger

logger = get_logger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v21.0"
GRAPH_API_URL = f"{GRAPH_BASE}/me/messages"


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


async def get_user_profile(
    platform_user_id: str,
    page_access_token: str,
) -> dict:
    """Get public info for a Facebook/Instagram user.

    GET /{psid}?fields=name,profile_pic
    """
    params = {
        "access_token": page_access_token,
        "fields": "name,profile_pic",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{GRAPH_BASE}/{platform_user_id}", params=params)
        resp.raise_for_status()
        return resp.json()
