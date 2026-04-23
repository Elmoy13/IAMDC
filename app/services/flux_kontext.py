"""Flux Kontext Pro via fal.ai — image-to-image generation.

Uses a reference product photo to generate professional scenes
with the real product via Flux Kontext Pro.
"""

import base64

import httpx

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

FAL_URL = "https://fal.run/fal-ai/flux-pro/kontext"
FAL_FLUX2_EDIT_URL = "https://fal.run/fal-ai/flux-2-pro/edit"


async def generate_image_with_reference(
    prompt: str,
    reference_image_url: str,
    aspect_ratio: str = "1:1",
) -> str:
    """Generate an image using Flux Kontext Pro with a reference image.

    Args:
        prompt: Scene description for product placement.
        reference_image_url: Public URL or data URL of the reference image.
        aspect_ratio: Aspect ratio for the generated image ("1:1", "9:16", "16:9", "3:4", "4:3").

    Returns:
        URL of the generated image.
    """
    headers = {
        "Authorization": f"Key {settings.fal_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": prompt,
        "image_url": reference_image_url,
        "aspect_ratio": aspect_ratio,
        "num_images": 1,
        "safety_tolerance": 5,
        "output_format": "png",
    }

    async with httpx.AsyncClient(timeout=300) as client:
        logger.info("flux_submit", prompt=prompt[:80], aspect_ratio=aspect_ratio)
        response = await client.post(FAL_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        logger.info("flux_response", keys=list(data.keys()))

        if "images" in data and len(data["images"]) > 0:
            return data["images"][0]["url"]

        raise RuntimeError(f"Flux returned no images. Response: {str(data)[:500]}")


async def generate_image_multi_reference(
    prompt: str,
    image_urls: list[str],
    aspect_ratio: str = "1:1",
) -> str:
    """Generate an image using Flux 2 Pro Edit with multiple reference images.

    Ideal for combining product + logo in a single scene.

    Args:
        prompt: Scene description referencing "first image" (product) and
                "second image" (logo), etc.
        image_urls: List of public URLs or data URLs (up to 9 images).
        aspect_ratio: Aspect ratio for the generated image.

    Returns:
        URL of the generated image.
    """
    headers = {
        "Authorization": f"Key {settings.fal_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": prompt,
        "image_urls": image_urls,
        "output_format": "png",
    }

    async with httpx.AsyncClient(timeout=300) as client:
        logger.info(
            "flux2_edit_submit",
            prompt=prompt[:80],
            num_images=len(image_urls),
        )
        response = await client.post(FAL_FLUX2_EDIT_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        logger.info("flux2_edit_response", keys=list(data.keys()))

        if "images" in data and len(data["images"]) > 0:
            return data["images"][0]["url"]

        raise RuntimeError(
            f"Flux 2 Pro Edit returned no images. Response: {str(data)[:500]}"
        )


async def download_image_as_base64(image_url: str) -> str:
    """Download an image from a URL and return it as a base64 data URL."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(image_url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "image/png")
        b64 = base64.b64encode(response.content).decode("utf-8")
        return f"data:{content_type};base64,{b64}"
