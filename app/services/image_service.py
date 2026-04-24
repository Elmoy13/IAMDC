import base64
import io

from PIL import Image

from app.core.logging import get_logger
from app.services.flux_kontext import generate_image_with_reference, download_image_as_base64

logger = get_logger(__name__)


def enrich_image_prompt(prompt: str) -> str:
    """Append strict no-text constraints to image prompts.

    AI image models sometimes generate fake text/logos/brand names on objects.
    These suffixes suppress that behaviour reliably.
    """
    suffix = (
        ", professional photography, high resolution, 4K quality, "
        "absolutely no text anywhere in the image, "
        "no words, no letters, no numbers, no logos, no brand names, "
        "no labels, no signs, no watermarks, no writing of any kind "
        "on any surface or object in the scene"
    )
    return prompt.strip() + suffix


async def generate_image_with_logo(prompt: str, context_image_b64: str) -> str:
    """Generate an image with Flux (fal.ai), then composite the user's logo.

    Args:
        prompt: Text prompt for image generation (should exclude text/logos).
        context_image_b64: Base64-encoded PNG of the user's logo with transparency.

    Returns:
        Data URL string: ``data:image/png;base64,...``
    """
    # 1. Generate the base image with Flux Pro
    enhanced_prompt = (
        f"{prompt}. "
        "The image must not contain any text, watermarks, or logos."
    )
    flux_url = await generate_image_with_reference(
        prompt=enhanced_prompt,
        reference_image_url="",
    )

    # Download and decode
    data_url = await download_image_as_base64(flux_url)
    # data_url is "data:<mime>;base64,<b64>" — extract raw bytes
    generated_b64 = data_url.split(",", 1)[1]
    generated_bytes = base64.b64decode(generated_b64)

    # 2. Decode logo
    logo_bytes = base64.b64decode(context_image_b64)

    base_image = Image.open(io.BytesIO(generated_bytes)).convert("RGBA")
    logo_image = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")

    # 3. Resize logo to 30% of base image width, keeping aspect ratio
    target_width = int(base_image.width * 0.3)
    aspect_ratio = logo_image.height / logo_image.width
    target_height = int(target_width * aspect_ratio)
    logo_resized = logo_image.resize(
        (target_width, target_height), Image.Resampling.LANCZOS
    )

    # 4. Center the logo on the base image
    x = (base_image.width - logo_resized.width) // 2
    y = (base_image.height - logo_resized.height) // 2

    # Composite: paste logo onto base using its alpha channel as mask
    base_image.paste(logo_resized, (x, y), logo_resized)

    # 5. Export as PNG base64 data URL
    buffer = io.BytesIO()
    base_image.save(buffer, format="PNG")
    result_b64 = base64.b64encode(buffer.getvalue()).decode()

    logger.info("image_generated_with_logo", width=base_image.width, height=base_image.height)
    return f"data:image/png;base64,{result_b64}"
