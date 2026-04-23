"""Parrilla drafts CRUD endpoints — scoped to the user's agency."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.logging import get_logger
from app.middleware.auth import get_user_agency
from app.schemas.draft import CreateDraftRequest, UpdateDraftRequest
from app.services.supabase_client import get_client

logger = get_logger(__name__)

router = APIRouter(prefix="/drafts", tags=["drafts"])


# ---------------------------------------------------------------------------
# POST /drafts — create a new draft
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_draft(
    payload: CreateDraftRequest,
    agency: dict = Depends(get_user_agency),
) -> dict:
    """Create a new parrilla draft."""
    client = get_client()
    result = (
        client.table("parrilla_drafts")
        .insert({
            "agency_id": agency["agency_id"],
            "brand_id": payload.brand_id,
            "user_id": agency["user_id"],
            "title": payload.title or "Parrilla sin nombre",
            "status": "draft",
            "chat_messages": [],
            "config": {},
        })
        .execute()
    )
    draft = result.data[0]
    logger.info("draft_created", draft_id=draft["id"])
    return draft


# ---------------------------------------------------------------------------
# GET /drafts — list drafts for this user/agency
# ---------------------------------------------------------------------------

@router.get("")
async def list_drafts(
    agency: dict = Depends(get_user_agency),
    draft_status: str = Query("draft", alias="status"),
    brand_id: str | None = Query(None),
) -> list[dict]:
    """List drafts for the current agency, filtered by status and optionally brand."""
    client = get_client()
    query = (
        client.table("parrilla_drafts")
        .select("*")
        .eq("agency_id", agency["agency_id"])
        .eq("status", draft_status)
        .order("updated_at", desc=True)
    )
    if brand_id:
        query = query.eq("brand_id", brand_id)
    result = query.execute()
    return result.data


# ---------------------------------------------------------------------------
# GET /drafts/{draft_id} — get a single draft
# ---------------------------------------------------------------------------

@router.get("/{draft_id}")
async def get_draft(
    draft_id: str,
    agency: dict = Depends(get_user_agency),
) -> dict:
    """Get a single draft by ID (must belong to the user's agency)."""
    client = get_client()
    result = (
        client.table("parrilla_drafts")
        .select("*")
        .eq("id", draft_id)
        .eq("agency_id", agency["agency_id"])
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Draft not found")
    return result.data


# ---------------------------------------------------------------------------
# PATCH /drafts/{draft_id} — auto-save / update
# ---------------------------------------------------------------------------

@router.patch("/{draft_id}")
async def update_draft(
    draft_id: str,
    payload: UpdateDraftRequest,
    agency: dict = Depends(get_user_agency),
) -> dict:
    """Update a draft (auto-save). Only non-null fields are written."""
    client = get_client()

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = (
        client.table("parrilla_drafts")
        .update(updates)
        .eq("id", draft_id)
        .eq("agency_id", agency["agency_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    return result.data[0]


# ---------------------------------------------------------------------------
# DELETE /drafts/{draft_id} — discard a draft
# ---------------------------------------------------------------------------

@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    draft_id: str,
    agency: dict = Depends(get_user_agency),
) -> None:
    """Delete a draft."""
    client = get_client()

    existing = (
        client.table("parrilla_drafts")
        .select("id")
        .eq("id", draft_id)
        .eq("agency_id", agency["agency_id"])
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    client.table("parrilla_drafts").delete().eq("id", draft_id).execute()
    logger.info("draft_deleted", draft_id=draft_id)
