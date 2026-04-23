from fastapi import APIRouter, Depends, HTTPException, status

from app.core.logging import get_logger
from app.middleware.auth import get_user_agency
from app.schemas.chat import BrandVisionRequest, BrandVisionResponse
from app.schemas.post import AnalyzeBrandRequest, AnalyzeBrandResponse
from app.services import brand_analyzer, vision_analyzer
from app.services.supabase_client import get_client
from app.services.storage_helper import upload_brand_logo

logger = get_logger(__name__)

router = APIRouter(prefix="/brand", tags=["brand"])


@router.post("/analyze", response_model=AnalyzeBrandResponse)
async def analyze_brand(
    payload: AnalyzeBrandRequest,
    agency: dict = Depends(get_user_agency),
) -> AnalyzeBrandResponse:
    """Extract brand colors and font suggestions from a logo."""
    try:
        result = await brand_analyzer.analyze_brand_from_logo(payload.logo_b64)
    except Exception as exc:
        logger.error("brand_analysis_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not analyse logo: {exc}",
        )
    return AnalyzeBrandResponse(**result)


@router.post("/analyze-vision", response_model=BrandVisionResponse)
async def analyze_brand_vision(
    payload: BrandVisionRequest,
    agency: dict = Depends(get_user_agency),
) -> BrandVisionResponse:
    """Full brand analysis: color extraction + AI vision analysis.

    Mode A (ephemeral): no brand_id → returns analysis without persisting.
    Mode B (persistent): brand_id present → uploads logo, persists analysis.
    """
    # 1. Run analysis
    try:
        colors = await brand_analyzer.analyze_brand_from_logo(payload.logo_b64)
    except Exception as exc:
        logger.error("brand_color_analysis_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not analyse logo colors: {exc}",
        )

    try:
        vision = await vision_analyzer.analyze_logo(payload.logo_b64)
    except Exception as exc:
        logger.error("brand_vision_analysis_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not analyse logo with vision: {exc}",
        )

    # Build unified analysis dict
    analysis = {
        "palette": colors.get("palette", []),
        "primary_color": colors.get("primary_color", "#000000"),
        "secondary_color": colors.get("secondary_color", "#ffffff"),
        "accent_colors": colors.get("palette", [])[2:] if len(colors.get("palette", [])) > 2 else [],
        "contrast_color": colors.get("contrast_color", "#ffffff"),
        "background_suggestion": colors.get("background_suggestion", "light"),
        "suggested_fonts": colors.get("suggested_fonts", []),
        "mood": vision.get("mood", ""),
        "style": vision.get("style", ""),
        "personality": vision.get("personality", []),
        "brand_name": vision.get("brand_name_detected", ""),
        "detected_typography": vision.get("color_mood", ""),
        "logo_description": vision.get("logo_description", ""),
        "target_audience": vision.get("target_audience", ""),
        "suggested_scenes": vision.get("suggested_scenes", []),
    }

    # Mode A — ephemeral
    if not payload.brand_id:
        return BrandVisionResponse(analysis=analysis, persisted=False)

    # Mode B — persistent: validate brand ownership, upload, persist
    client = get_client()
    existing = (
        client.table("brands")
        .select("id")
        .eq("id", payload.brand_id)
        .eq("agency_id", agency["agency_id"])
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Brand not found")

    # Upload logo to brand-assets bucket
    logo_url, _storage_path = await upload_brand_logo(
        agency_id=agency["agency_id"],
        brand_id=payload.brand_id,
        logo_b64=payload.logo_b64,
    )

    # Persist to brands table
    client.table("brands").update({
        "logo_url": logo_url,
        "vision_analysis": analysis,
        "detected_at": "now()",
        "primary_color": analysis["primary_color"],
        "secondary_color": analysis["secondary_color"],
        "accent_color": analysis["accent_colors"][0] if analysis["accent_colors"] else "#888888",
        "contrast_color": analysis["contrast_color"],
    }).eq("id", payload.brand_id).execute()

    logger.info("brand_vision_persisted", brand_id=payload.brand_id)

    return BrandVisionResponse(
        analysis=analysis,
        logo_url=logo_url,
        persisted=True,
    )
