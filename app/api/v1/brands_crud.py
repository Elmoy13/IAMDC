"""Brands CRUD endpoints — scoped to the user's agency."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.logging import get_logger
from app.middleware.auth import get_user_agency
from app.schemas.brand import (
    BrandListResponse,
    BrandResponse,
    CreateBrandRequest,
    UpdateBrandRequest,
)
from app.services.supabase_client import get_client

logger = get_logger(__name__)

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("", response_model=BrandListResponse)
async def list_brands(
    agency: dict = Depends(get_user_agency),
) -> BrandListResponse:
    """List all brands belonging to the user's agency."""
    client = get_client()
    result = (
        client.table("brands")
        .select("*")
        .eq("agency_id", agency["agency_id"])
        .order("created_at", desc=True)
        .execute()
    )
    return BrandListResponse(brands=result.data)


@router.get("/{brand_id}", response_model=BrandResponse)
async def get_brand(
    brand_id: str,
    agency: dict = Depends(get_user_agency),
) -> BrandResponse:
    """Get a single brand by ID (must belong to the user's agency)."""
    client = get_client()
    result = (
        client.table("brands")
        .select("*")
        .eq("id", brand_id)
        .eq("agency_id", agency["agency_id"])
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Brand not found")
    return BrandResponse(**result.data)


@router.post("", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(
    payload: CreateBrandRequest,
    agency: dict = Depends(get_user_agency),
) -> BrandResponse:
    """Create a new brand for the user's agency."""
    client = get_client()
    row = payload.model_dump(exclude_none=True)
    row["agency_id"] = agency["agency_id"]
    result = client.table("brands").insert(row).execute()
    brand = result.data[0]
    logger.info("brand_created", brand_id=brand["id"], agency_id=agency["agency_id"])
    return BrandResponse(**brand)


@router.patch("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    brand_id: str,
    payload: UpdateBrandRequest,
    agency: dict = Depends(get_user_agency),
) -> BrandResponse:
    """Update an existing brand (must belong to the user's agency)."""
    client = get_client()

    # Verify ownership
    existing = (
        client.table("brands")
        .select("id")
        .eq("id", brand_id)
        .eq("agency_id", agency["agency_id"])
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Brand not found")

    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = (
        client.table("brands")
        .update(fields)
        .eq("id", brand_id)
        .execute()
    )
    logger.info("brand_updated", brand_id=brand_id)
    return BrandResponse(**result.data[0])


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(
    brand_id: str,
    agency: dict = Depends(get_user_agency),
) -> None:
    """Delete a brand (must belong to the user's agency)."""
    client = get_client()

    existing = (
        client.table("brands")
        .select("id")
        .eq("id", brand_id)
        .eq("agency_id", agency["agency_id"])
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Brand not found")

    client.table("brands").delete().eq("id", brand_id).execute()
    logger.info("brand_deleted", brand_id=brand_id)
