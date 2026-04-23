from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.middleware.auth import get_user_agency
from app.schemas.chat import ProductAnalyzeRequest, ProductAnalyzeResponse
from app.services import vision_analyzer
from app.services.supabase_client import get_client
from app.services.storage_helper import upload_product_image, delete_storage_object

logger = get_logger(__name__)

router = APIRouter(prefix="/product", tags=["product"])


# ---------------------------------------------------------------------------
# Schemas for product CRUD (small, co-located here)
# ---------------------------------------------------------------------------

class UpdateProductRequest(BaseModel):
    name: Optional[str] = None
    display_order: Optional[int] = None
    is_primary: Optional[bool] = None


# ---------------------------------------------------------------------------
# POST /product/analyze — ephemeral + persistent mode
# ---------------------------------------------------------------------------

@router.post("/analyze")
async def analyze_product(
    payload: ProductAnalyzeRequest,
    agency: dict = Depends(get_user_agency),
) -> dict:
    """Analyze a product image with Nova Pro vision.

    Mode A (ephemeral): no brand_id or persist=False → returns analysis only.
    Mode B (persistent): brand_id + persist=True → uploads image, stores in brand_products.
    """
    try:
        result = await vision_analyzer.analyze_product(payload.product_b64)
    except Exception as exc:
        logger.error("product_analysis_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not analyse product image: {exc}",
        )

    # Mode A — ephemeral
    if not payload.brand_id or not payload.persist:
        return {
            "analysis": result,
            "persisted": False,
        }

    # Mode B — persistent
    client = get_client()

    # Validate brand ownership
    brand = (
        client.table("brands")
        .select("id")
        .eq("id", payload.brand_id)
        .eq("agency_id", agency["agency_id"])
        .maybe_single()
        .execute()
    )
    if not brand.data:
        raise HTTPException(status_code=404, detail="Brand not found")

    # Upload product image to storage
    image_url, storage_path = await upload_product_image(
        agency_id=agency["agency_id"],
        brand_id=payload.brand_id,
        image_b64=payload.product_b64,
    )

    # Insert into brand_products
    row = {
        "brand_id": payload.brand_id,
        "name": payload.product_name or result.get("product_type", "Product"),
        "image_url": image_url,
        "storage_path": storage_path,
        "vision_analysis": result,
        "analyzed_at": "now()",
        "display_order": payload.display_order,
    }
    insert_result = client.table("brand_products").insert(row).execute()
    product = insert_result.data[0]

    logger.info("product_persisted", product_id=product["id"], brand_id=payload.brand_id)

    return {
        "product_id": product["id"],
        "image_url": image_url,
        "analysis": result,
        "persisted": True,
    }


# ---------------------------------------------------------------------------
# GET /product/brands/{brand_id}/products — list products for a brand
# ---------------------------------------------------------------------------

@router.get("/brands/{brand_id}/products")
async def list_brand_products(
    brand_id: str,
    agency: dict = Depends(get_user_agency),
) -> list[dict]:
    """List all products belonging to a brand (scoped to agency)."""
    client = get_client()

    # Validate brand ownership
    brand = (
        client.table("brands")
        .select("id")
        .eq("id", brand_id)
        .eq("agency_id", agency["agency_id"])
        .maybe_single()
        .execute()
    )
    if not brand.data:
        raise HTTPException(status_code=404, detail="Brand not found")

    result = (
        client.table("brand_products")
        .select("*")
        .eq("brand_id", brand_id)
        .order("display_order")
        .execute()
    )
    return result.data


# ---------------------------------------------------------------------------
# PATCH /product/{product_id} — update product metadata
# ---------------------------------------------------------------------------

@router.patch("/{product_id}")
async def update_product(
    product_id: str,
    payload: UpdateProductRequest,
    agency: dict = Depends(get_user_agency),
) -> dict:
    """Update a product's name, display_order, or is_primary."""
    client = get_client()

    # Fetch product + validate ownership via brand
    product = (
        client.table("brand_products")
        .select("id, brand_id")
        .eq("id", product_id)
        .maybe_single()
        .execute()
    )
    if not product.data:
        raise HTTPException(status_code=404, detail="Product not found")

    brand = (
        client.table("brands")
        .select("id")
        .eq("id", product.data["brand_id"])
        .eq("agency_id", agency["agency_id"])
        .maybe_single()
        .execute()
    )
    if not brand.data:
        raise HTTPException(status_code=404, detail="Product not found")

    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = (
        client.table("brand_products")
        .update(fields)
        .eq("id", product_id)
        .execute()
    )
    return result.data[0]


# ---------------------------------------------------------------------------
# DELETE /product/{product_id} — delete product + storage file
# ---------------------------------------------------------------------------

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: str,
    agency: dict = Depends(get_user_agency),
) -> None:
    """Delete a product and its storage file."""
    client = get_client()

    product = (
        client.table("brand_products")
        .select("id, brand_id, storage_path")
        .eq("id", product_id)
        .maybe_single()
        .execute()
    )
    if not product.data:
        raise HTTPException(status_code=404, detail="Product not found")

    brand = (
        client.table("brands")
        .select("id")
        .eq("id", product.data["brand_id"])
        .eq("agency_id", agency["agency_id"])
        .maybe_single()
        .execute()
    )
    if not brand.data:
        raise HTTPException(status_code=404, detail="Product not found")

    # Delete storage file
    if product.data.get("storage_path"):
        try:
            await delete_storage_object(product.data["storage_path"])
        except Exception as exc:
            logger.warning("product_storage_delete_failed", error=str(exc))

    # Delete DB row
    client.table("brand_products").delete().eq("id", product_id).execute()
    logger.info("product_deleted", product_id=product_id)
