"""CRUD endpoints for connected channels."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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


# ── Endpoints ─────────────────────────────────────────────

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
