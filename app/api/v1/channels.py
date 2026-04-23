"""CRUD endpoints for connected channels."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.middleware.auth import get_current_user, get_user_agency
from app.services import channel_service

router = APIRouter(prefix="/channels", tags=["channels"])


# ── Schemas ───────────────────────────────────────────────

class ChannelBrandInfo(BaseModel):
    brand_id: str
    is_primary: bool


class ChannelInfo(BaseModel):
    id: str
    platform: str | None
    page_id: str | None
    created_at: str | None
    brands: list[ChannelBrandInfo]


class ChannelBrandDetail(BaseModel):
    id: str
    channel_id: str
    brand_id: str
    is_primary: bool
    priority: int
    trigger_keywords: list[str] | None = None


class ChannelBrandInput(BaseModel):
    brand_id: str
    is_primary: bool = False
    priority: int = Field(default=1, ge=1)
    trigger_keywords: list[str] | None = None


class ChannelBrandsUpdate(BaseModel):
    brands: list[ChannelBrandInput]


class PlatformOption(BaseModel):
    id: str
    display_name: str
    category: str
    status: str  # "active", "beta", "coming_soon"
    icon_name: str
    brand_color: str
    description: str
    order: int


PLATFORMS = [
    PlatformOption(
        id="facebook",
        display_name="Facebook Messenger",
        category="meta",
        status="active",
        icon_name="facebook",
        brand_color="#1877F2",
        description="Recibe y responde mensajes de tu Facebook Page con IA",
        order=1,
    ),
    PlatformOption(
        id="instagram",
        display_name="Instagram DMs",
        category="meta",
        status="coming_soon",
        icon_name="instagram",
        brand_color="#E4405F",
        description="Automatiza DMs de tu cuenta Business de Instagram",
        order=2,
    ),
    PlatformOption(
        id="whatsapp",
        display_name="WhatsApp Business",
        category="meta",
        status="coming_soon",
        icon_name="message-circle",
        brand_color="#25D366",
        description="Conversa con clientes por WhatsApp con flujos automatizados",
        order=3,
    ),
    PlatformOption(
        id="web_chat",
        display_name="Chat en tu sitio web",
        category="web",
        status="coming_soon",
        icon_name="globe",
        brand_color="#6366F1",
        description="Widget embebible para el sitio web de tu marca",
        order=4,
    ),
    PlatformOption(
        id="tiktok",
        display_name="TikTok Business",
        category="social",
        status="coming_soon",
        icon_name="music",
        brand_color="#000000",
        description="Gestiona DMs de tu cuenta Business de TikTok",
        order=5,
    ),
    PlatformOption(
        id="email",
        display_name="Email",
        category="email",
        status="coming_soon",
        icon_name="mail",
        brand_color="#64748B",
        description="Recibe emails de soporte y responde con IA",
        order=6,
    ),
    PlatformOption(
        id="telegram",
        display_name="Telegram Bot",
        category="social",
        status="coming_soon",
        icon_name="send",
        brand_color="#229ED9",
        description="Bot de Telegram con IA para tu canal",
        order=7,
    ),
    PlatformOption(
        id="twitter_x",
        display_name="Twitter / X DMs",
        category="social",
        status="coming_soon",
        icon_name="twitter",
        brand_color="#000000",
        description="Responde DMs de X automáticamente",
        order=8,
    ),
    PlatformOption(
        id="google_business",
        display_name="Google Business Messages",
        category="voice",
        status="coming_soon",
        icon_name="map-pin",
        brand_color="#4285F4",
        description="Mensajes que llegan desde tu perfil de Google Business",
        order=9,
    ),
]

_PLATFORMS_BY_ID = {p.id: p for p in PLATFORMS}


# ── Endpoints ─────────────────────────────────────────────

@router.get("/platforms", response_model=list[PlatformOption])
async def list_platforms(user: dict = Depends(get_current_user)):
    """List all available channel platforms (active + coming soon)."""
    return PLATFORMS

@router.get("/by-agency/{agency_id}", response_model=list[ChannelInfo])
async def list_channels(
    agency_id: UUID,
    user: dict = Depends(get_current_user),
    agency: dict = Depends(get_user_agency),
    db: AsyncSession = Depends(get_db),
):
    """List all connected channels for an agency.

    **Requires:** JWT authentication. User must belong to the agency.

    **Returns:** list of channels with their associated brands.
    """
    if str(agency["agency_id"]) != str(agency_id):
        raise HTTPException(403, "No access to this agency")
    return await channel_service.list_channels_by_agency(db, agency_id)


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: UUID,
    agency_id: UUID = Query(..., description="Agency that owns the channel"),
    user: dict = Depends(get_current_user),
    agency: dict = Depends(get_user_agency),
    db: AsyncSession = Depends(get_db),
):
    """Delete (disconnect) a channel.

    Unsubscribes the page from the Meta webhook and removes the channel
    from the database.

    **Requires:** JWT authentication. User must belong to the agency.

    **Returns:** ``{"status": "deleted"}``
    """
    if str(agency["agency_id"]) != str(agency_id):
        raise HTTPException(403, "No access to this agency")
    await channel_service.delete_channel(db, channel_id, agency_id)
    return {"status": "deleted"}


@router.get("/{channel_id}/brands", response_model=list[ChannelBrandDetail])
async def list_channel_brands(
    channel_id: UUID,
    agency_id: UUID = Query(..., description="Agency that owns the channel"),
    user: dict = Depends(get_current_user),
    agency: dict = Depends(get_user_agency),
    db: AsyncSession = Depends(get_db),
):
    """List all brands linked to a channel, ordered by priority."""
    if str(agency["agency_id"]) != str(agency_id):
        raise HTTPException(403, "No access to this agency")
    return await channel_service.list_channel_brands(db, channel_id, agency_id)


@router.put("/{channel_id}/brands", response_model=list[ChannelBrandDetail])
async def replace_channel_brands(
    channel_id: UUID,
    payload: ChannelBrandsUpdate,
    agency_id: UUID = Query(..., description="Agency that owns the channel"),
    user: dict = Depends(get_current_user),
    agency: dict = Depends(get_user_agency),
    db: AsyncSession = Depends(get_db),
):
    """Atomic replace of all brand assignments for a channel.

    Deletes existing channel_brands and inserts the new set.
    Validates exactly one brand is marked as primary.
    """
    if str(agency["agency_id"]) != str(agency_id):
        raise HTTPException(403, "No access to this agency")

    primary_count = sum(1 for b in payload.brands if b.is_primary)
    if len(payload.brands) > 0 and primary_count != 1:
        raise HTTPException(422, "Exactly one brand must be marked as primary")

    return await channel_service.replace_channel_brands(
        db, channel_id, agency_id, payload.brands,
    )
