"""OAuth flow with Meta for Developers.

Token exchange, long-lived refresh, webhook subscription, handover protocol.
"""

from urllib.parse import urlencode

import httpx

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v21.0"


def build_authorize_url(state: str) -> str:
    """Build the Facebook OAuth authorize URL.

    Args:
        state: unique anti-CSRF token (validated on callback).

    Returns:
        Full URL like ``https://www.facebook.com/v21.0/dialog/oauth?...``
    """
    params = {
        "client_id": settings.meta_app_id,
        "redirect_uri": settings.meta_oauth_redirect_uri,
        "state": state,
        "scope": settings.meta_oauth_scopes,
        "response_type": "code",
        "auth_type": "reauthenticate",
    }
    return f"https://www.facebook.com/v21.0/dialog/oauth?{urlencode(params)}"


async def exchange_code_for_user_token(code: str) -> str:
    """Exchange the OAuth code for a short-lived user access token.

    Calls ``GET /oauth/access_token``.
    """
    params = {
        "client_id": settings.meta_app_id,
        "client_secret": settings.meta_app_secret,
        "redirect_uri": settings.meta_oauth_redirect_uri,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{GRAPH_BASE}/oauth/access_token", params=params)
        resp.raise_for_status()
        data = resp.json()

    token = data.get("access_token")
    if not token:
        raise ValueError("No access_token in Meta response")

    logger.info("oauth_code_exchanged", expires_in=data.get("expires_in"))
    return token


async def exchange_for_long_lived_user_token(short_token: str) -> dict:
    """Exchange a short-lived user token for a long-lived one (~60 days).

    Calls ``GET /oauth/access_token?grant_type=fb_exchange_token&...``
    """
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": settings.meta_app_id,
        "client_secret": settings.meta_app_secret,
        "fb_exchange_token": short_token,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{GRAPH_BASE}/oauth/access_token", params=params)
        resp.raise_for_status()
        data = resp.json()

    if not data.get("access_token"):
        raise ValueError("No long-lived token returned")

    logger.info("long_lived_user_token_obtained", expires_in=data.get("expires_in"))
    return {
        "access_token": data["access_token"],
        "token_type": data.get("token_type", "bearer"),
        "expires_in": data.get("expires_in"),
    }


async def get_user_pages(long_lived_user_token: str) -> list[dict]:
    """List Facebook pages the authenticated user manages.

    Each page includes its own page access token (long-lived automatically
    when derived from a long-lived user token).

    Calls ``GET /me/accounts``.
    """
    params = {
        "access_token": long_lived_user_token,
        "fields": (
            "id,name,access_token,category,tasks,"
            "instagram_business_account{id,username,name,profile_picture_url}"
        ),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{GRAPH_BASE}/me/accounts", params=params)
        resp.raise_for_status()
        data = resp.json()

    pages = data.get("data", [])
    logger.info("user_pages_fetched", count=len(pages))
    return pages


async def subscribe_page_to_webhook(
    page_id: str,
    page_access_token: str,
) -> bool:
    """Subscribe a page to the AIMDC webhook for messages.

    Calls ``POST /{page_id}/subscribed_apps`` with fields
    ``messages,messaging_postbacks``.
    """
    params = {
        "access_token": page_access_token,
        "subscribed_fields": "messages,messaging_postbacks",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GRAPH_BASE}/{page_id}/subscribed_apps", params=params
        )
        resp.raise_for_status()
        data = resp.json()

    success = data.get("success", False)
    logger.info("page_subscribed_to_webhook", page_id=page_id, success=success)
    return success


async def unsubscribe_page_from_webhook(
    page_id: str,
    page_access_token: str,
) -> bool:
    """Unsubscribe a page from the webhook (on channel disconnect).

    Calls ``DELETE /{page_id}/subscribed_apps``.
    """
    params = {"access_token": page_access_token}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(
            f"{GRAPH_BASE}/{page_id}/subscribed_apps", params=params
        )
        resp.raise_for_status()
        data = resp.json()

    return data.get("success", False)


async def handover_to_app(page_id: str, page_access_token: str) -> bool:
    """Handover Protocol: claim primary receiver for the page.

    This disables native Meta auto-replies and other integrations so that
    AIMDC handles all incoming messages.

    Re-posts to ``/{page_id}/subscribed_apps`` which is idempotent.
    """
    params = {
        "access_token": page_access_token,
        "subscribed_fields": "messages,messaging_postbacks",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GRAPH_BASE}/{page_id}/subscribed_apps", params=params
        )
        if resp.status_code >= 400:
            logger.warning(
                "handover_failed_non_critical",
                page_id=page_id,
                status=resp.status_code,
                body=resp.text[:200],
            )
            return False

    logger.info("handover_to_app_done", page_id=page_id)
    return True


async def get_page_info(page_id: str, page_access_token: str) -> dict:
    """Fetch public info for a page (name, category, picture, etc.).

    Calls ``GET /{page_id}?fields=...``.
    """
    params = {
        "access_token": page_access_token,
        "fields": "id,name,category,picture.type(large),username,fan_count",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{GRAPH_BASE}/{page_id}", params=params)
        resp.raise_for_status()
        return resp.json()
