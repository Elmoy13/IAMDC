"""Helpers for uploading / deleting files in the brand-assets storage bucket."""

import base64
import uuid
from datetime import datetime

from app.core.logging import get_logger
from app.services.supabase_client import get_client

logger = get_logger(__name__)

BRAND_ASSETS_BUCKET = "brand-assets"


def _strip_b64_prefix(b64: str) -> bytes:
    """Decode a base64 string (with optional data-URL prefix) to bytes."""
    raw = b64
    if b64.startswith("data:"):
        raw = b64.split(",", 1)[1]
    return base64.b64decode(raw)


async def upload_brand_logo(
    agency_id: str,
    brand_id: str,
    logo_b64: str,
    ext: str = "png",
) -> tuple[str, str]:
    """Upload a logo to brand-assets and return (public_url, storage_path)."""
    file_bytes = _strip_b64_prefix(logo_b64)
    timestamp = int(datetime.now().timestamp())
    storage_path = f"{agency_id}/{brand_id}/logo_{timestamp}.{ext}"

    client = get_client()
    client.storage.from_(BRAND_ASSETS_BUCKET).upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": f"image/{ext}", "upsert": "true"},
    )

    public_url = client.storage.from_(BRAND_ASSETS_BUCKET).get_public_url(storage_path)
    logger.info("brand_logo_uploaded", brand_id=brand_id, path=storage_path)
    return public_url, storage_path


async def upload_product_image(
    agency_id: str,
    brand_id: str,
    image_b64: str,
    ext: str = "png",
) -> tuple[str, str]:
    """Upload a product photo and return (public_url, storage_path)."""
    file_bytes = _strip_b64_prefix(image_b64)
    product_uuid = str(uuid.uuid4())
    timestamp = int(datetime.now().timestamp())
    storage_path = f"{agency_id}/{brand_id}/products/product_{product_uuid}_{timestamp}.{ext}"

    client = get_client()
    client.storage.from_(BRAND_ASSETS_BUCKET).upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": f"image/{ext}"},
    )

    public_url = client.storage.from_(BRAND_ASSETS_BUCKET).get_public_url(storage_path)
    logger.info("product_image_uploaded", brand_id=brand_id, path=storage_path)
    return public_url, storage_path


async def delete_storage_object(storage_path: str) -> None:
    """Delete an object from the brand-assets bucket."""
    client = get_client()
    client.storage.from_(BRAND_ASSETS_BUCKET).remove([storage_path])
    logger.info("storage_object_deleted", path=storage_path)
