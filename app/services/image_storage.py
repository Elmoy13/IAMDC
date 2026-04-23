"""Image storage — convert base64 product images to data URLs for Flux Kontext.

fal.ai accepts data: URIs directly in the image_url field,
so no external upload or public URL is needed.
"""

from app.core.logging import get_logger

logger = get_logger(__name__)


async def upload_image_to_fal(image_b64: str) -> str:
    """Convert a base64 image string into a data URL that fal.ai can consume.

    fal.ai supports data: URIs directly, avoiding the need for a public URL.
    """
    if image_b64.startswith("data:"):
        logger.info("image_ready_as_data_url")
        return image_b64

    # Raw base64 without prefix — add one
    logger.info("image_converted_to_data_url")
    return f"data:image/png;base64,{image_b64}"
