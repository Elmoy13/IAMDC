"""OAuth flow endpoints for Meta (Facebook / Instagram).

Handles the three-step flow:
1. ``GET /start`` — returns Facebook authorize URL + anti-CSRF state
2. ``GET /callback`` — Meta redirects here after user authorizes
3. ``POST /connect`` — frontend calls to link a selected page to a brand
"""

import datetime as dt
import json
import secrets
from typing import Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import settings
from app.core.logging import get_logger
from app.middleware.auth import get_current_user, get_user_agency
from app.services import meta_oauth

logger = get_logger(__name__)

router = APIRouter(prefix="/oauth/meta", tags=["oauth"])

# ── In-memory OAuth state store (Redis in production) ─────
# Key: state string  →  Value: metadata dict
# Key: "user_token:<user_id>"  →  Value: cached tokens + pages after callback
_oauth_states: dict[str, dict] = {}
_STATE_TTL_SECONDS = 600  # 10 min


# ── Schemas ───────────────────────────────────────────────

class OAuthStartResponse(BaseModel):
    authorize_url: str
    state: str


class ConnectChannelRequest(BaseModel):
    page_id: str
    agency_id: UUID
    brand_id: UUID


class ConnectChannelResponse(BaseModel):
    channel_id: UUID
    page_id: str
    page_name: str
    brand_id: UUID
    subscribed: bool


# ── Endpoints ─────────────────────────────────────────────

@router.get("/start", response_model=OAuthStartResponse)
async def start_oauth(
    agency_id: UUID = Query(..., description="Agency that will own the channel"),
    brand_id: UUID = Query(..., description="Brand to associate with the channel"),
    user: dict = Depends(get_current_user),
    agency: dict = Depends(get_user_agency),
):
    """Start the Meta OAuth flow.

    The frontend calls this endpoint, receives a Facebook authorization URL
    and an anti-CSRF ``state`` token, then opens the URL in a popup/redirect.

    **Requires:** JWT authentication. User must belong to the given agency.

    **Returns:** ``authorize_url`` to redirect to Facebook, ``state`` to track the flow.
    """
    if str(agency["agency_id"]) != str(agency_id):
        raise HTTPException(403, "No access to this agency")

    state = secrets.token_urlsafe(32)

    _oauth_states[state] = {
        "user_id": user["user_id"],
        "agency_id": str(agency_id),
        "brand_id": str(brand_id),
        "created_at": dt.datetime.utcnow(),
    }

    authorize_url = meta_oauth.build_authorize_url(state=state)

    return OAuthStartResponse(authorize_url=authorize_url, state=state)


@router.get("/callback")
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    """OAuth callback that Meta redirects to after user authorization.

    **No JWT required** — this is called by Meta's redirect, not by the frontend.
    Authorization is validated via the ``state`` anti-CSRF token.

    On success, redirects the user to the frontend page-selection screen with
    public page info (no tokens are exposed to the frontend).
    """
    if error:
        logger.warning("oauth_user_cancelled", error=error, desc=error_description)
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings/channels?oauth_error={error}",
            status_code=302,
        )

    if not code or not state:
        raise HTTPException(400, "Missing code or state")

    # Validate state (anti-CSRF)
    state_data = _oauth_states.pop(state, None)
    if not state_data:
        raise HTTPException(400, "Invalid or expired state")

    age = (dt.datetime.utcnow() - state_data["created_at"]).total_seconds()
    if age > _STATE_TTL_SECONDS:
        raise HTTPException(400, "State expired")

    # Step 1: exchange code → short-lived user token
    try:
        short_token = await meta_oauth.exchange_code_for_user_token(code)
    except Exception as exc:
        logger.error("oauth_exchange_failed", error=str(exc))
        raise HTTPException(502, "Failed to exchange code with Meta")

    # Step 2: short-lived → long-lived user token
    try:
        long_lived = await meta_oauth.exchange_for_long_lived_user_token(short_token)
    except Exception as exc:
        logger.error("oauth_long_lived_failed", error=str(exc))
        raise HTTPException(502, "Failed to get long-lived token")

    # Step 3: list user's pages
    try:
        pages = await meta_oauth.get_user_pages(long_lived["access_token"])
    except Exception as exc:
        logger.error("oauth_get_pages_failed", error=str(exc))
        raise HTTPException(502, "Failed to list user pages")

    # Cache tokens + pages keyed by user_id so /connect can use them
    cache_key = f"user_token:{state_data['user_id']}"
    _oauth_states[cache_key] = {
        "long_lived_user_token": long_lived["access_token"],
        "pages": pages,
        "agency_id": state_data["agency_id"],
        "brand_id": state_data["brand_id"],
        "created_at": dt.datetime.utcnow(),
    }

    # Build safe redirect with only public page info (no tokens)
    pages_public = [
        {
            "id": p["id"],
            "name": p["name"],
            "category": p.get("category"),
            "has_instagram": bool(p.get("instagram_business_account")),
        }
        for p in pages
    ]

    pages_encoded = quote(json.dumps(pages_public))
    redirect_url = (
        f"{settings.frontend_url}/settings/channels/select"
        f"?agency_id={state_data['agency_id']}"
        f"&brand_id={state_data['brand_id']}"
        f"&pages={pages_encoded}"
    )

    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/connect", response_model=ConnectChannelResponse)
async def connect_channel(
    body: ConnectChannelRequest,
    user: dict = Depends(get_current_user),
    agency: dict = Depends(get_user_agency),
    db: AsyncSession = Depends(get_db),
):
    """Connect a Facebook page to a brand after OAuth authorization.

    The frontend calls this after the user selects which page to connect
    from the page-selection screen.

    **Requires:** JWT authentication. User must have completed OAuth first
    (tokens cached from the callback step).

    **Returns:** the newly created channel with subscription status.
    """
    if str(agency["agency_id"]) != str(body.agency_id):
        raise HTTPException(403, "No access to this agency")

    # Retrieve cached tokens from the OAuth callback
    cache_key = f"user_token:{user['user_id']}"
    cached = _oauth_states.get(cache_key)
    if not cached:
        raise HTTPException(400, "OAuth session expired. Please start the flow again.")

    # TTL check on cached tokens
    age = (dt.datetime.utcnow() - cached["created_at"]).total_seconds()
    if age > _STATE_TTL_SECONDS:
        _oauth_states.pop(cache_key, None)
        raise HTTPException(400, "OAuth session expired. Please start the flow again.")

    # Find the selected page
    page = next((p for p in cached["pages"] if p["id"] == body.page_id), None)
    if not page:
        raise HTTPException(404, "Page not found in user's authorized pages")

    page_access_token = page["access_token"]

    # Subscribe page to webhook
    subscribed = await meta_oauth.subscribe_page_to_webhook(
        page_id=body.page_id,
        page_access_token=page_access_token,
    )
    if not subscribed:
        raise HTTPException(502, "Failed to subscribe page to webhook")

    # Handover Protocol (non-blocking if it fails)
    await meta_oauth.handover_to_app(
        page_id=body.page_id,
        page_access_token=page_access_token,
    )

    # Persist channel with encrypted token
    from app.services.channel_service import create_channel_with_encrypted_token

    channel = await create_channel_with_encrypted_token(
        db=db,
        agency_id=body.agency_id,
        user_id=UUID(user["user_id"]),
        platform="facebook",
        page_id=body.page_id,
        page_name=page["name"],
        page_access_token=page_access_token,
        brand_id=body.brand_id,
    )

    # Clean up cached tokens
    _oauth_states.pop(cache_key, None)

    logger.info(
        "channel_connected",
        channel_id=str(channel.id),
        agency_id=str(body.agency_id),
        brand_id=str(body.brand_id),
        page_id=body.page_id,
    )

    return ConnectChannelResponse(
        channel_id=channel.id,
        page_id=body.page_id,
        page_name=page["name"],
        brand_id=body.brand_id,
        subscribed=subscribed,
    )
