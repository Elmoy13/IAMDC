"""Nano Banana 2 Edit via fal.ai — post-process images with logo + text.

Takes a Flux-generated scene image and enhances it by integrating the brand
logo and/or headline text using Nano Banana 2 Edit's multi-reference
capabilities.
"""

import httpx

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

NANO_BANANA_EDIT_URL = "https://fal.run/fal-ai/nano-banana-2/edit"


async def enhance_post_image(
    base_image_url: str,
    logo_url: str | None = None,
    headline: str | None = None,
    cta: str | None = None,
    brand_colors: dict | None = None,
    include_logo: bool = True,
    include_text: bool = True,
    language: str = "es",
) -> str:
    """Take a base image (from Flux) and add logo + text using Nano Banana 2 Edit.

    Args:
        base_image_url: URL of the Flux-generated scene image.
        logo_url: Public/data URL of the brand logo.
        headline: Headline text to render on the image.
        cta: Call-to-action text for a button-style element.
        brand_colors: Dict with primary_color, secondary_color keys.
        include_logo: Whether to integrate the logo.
        include_text: Whether to add headline/CTA text.
        language: 'es' or 'en' — language of the text to render.

    Returns:
        URL of the enhanced image from Nano Banana 2.
    """
    headers = {
        "Authorization": f"Key {settings.fal_key}",
        "Content-Type": "application/json",
    }

    # Build reference image list
    image_urls = [base_image_url]
    if include_logo and logo_url:
        image_urls.append(logo_url)

    # Build the editing prompt
    prompt_parts = []

    if include_logo and logo_url:
        prompt_parts.append(
            "Integrate the logo from the second reference image naturally into the scene. "
            "Place it clearly visible on a surface in the scene such as a coaster, "
            "a small framed sign, a napkin, or a neon sign on the wall. "
            "The logo must be sharp, fully visible, and recognizable."
        )

    if include_text and headline:
        primary_color = (
            brand_colors.get("primary_color", "#FFFFFF") if brand_colors else "#FFFFFF"
        )

        lang_name = "Spanish" if language == "es" else "English"
        text_instruction = (
            f"Add the following text in {lang_name} with perfect typography "
            f"at the bottom of the image. "
            f"The headline text must say exactly: '{headline}'. "
            f"Use a premium, clean sans-serif font. "
            f"The text should be white or light colored with a subtle dark gradient "
            f"or semi-transparent dark bar behind it for readability. "
            f"The text must be perfectly spelled, crisp, and legible. "
        )

        if cta:
            text_instruction += (
                f"Below the headline, add a small button-style element "
                f"with the text '{cta}' using the brand color {primary_color}. "
            )

        prompt_parts.append(text_instruction)

    prompt_parts.append(
        "Keep the original scene, product, lighting, and composition exactly the same. "
        "Only add the logo and text elements described above. "
        "The result should look like a professional social media advertisement."
    )

    full_prompt = " ".join(prompt_parts)

    payload = {
        "prompt": full_prompt,
        "image_urls": image_urls,
        "output_format": "png",
        "safety_tolerance": "4",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        logger.info(
            "nano_banana_submit",
            include_logo=include_logo,
            include_text=include_text,
            num_refs=len(image_urls),
        )
        response = await client.post(
            NANO_BANANA_EDIT_URL, json=payload, headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        logger.info("nano_banana_response", keys=list(data.keys()))

        if "images" in data and len(data["images"]) > 0:
            return data["images"][0]["url"]

        raise RuntimeError(
            f"Nano Banana 2 Edit returned no images. Response: {str(data)[:500]}"
        )
