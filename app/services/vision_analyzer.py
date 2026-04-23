"""Visual analysis of logos and products using Amazon Nova Pro (multimodal).

Uses the same Bedrock client already configured in the project.
"""

import asyncio
import base64
import json

from app.core.logging import get_logger
from app.services.template_generator import _get_bedrock_client
from app.config import settings

logger = get_logger(__name__)

VISION_MODEL_ID = "amazon.nova-pro-v1:0"

_LOGO_PROMPT = """\
Analyze this logo image in detail. Respond ONLY in JSON format:
{
  "brand_name_detected": "name if visible in the logo, or 'unknown'",
  "logo_description": "detailed visual description of the logo (shapes, icons, characters)",
  "style": "minimalist/vintage/modern/playful/corporate/handmade/etc",
  "personality": ["trait1", "trait2", "trait3"],
  "target_audience": "who this logo seems designed for",
  "mood": "the emotional mood the logo evokes (e.g. party, elegant, casual, energetic)",
  "suggested_scenes": ["scene1", "scene2", "scene3", "scene4", "scene5"],
  "color_mood": "warm/cool/neutral/vibrant/muted"
}"""

_PRODUCT_PROMPT = """\
Analyze this product image in detail. Respond ONLY in JSON format:
{
  "product_type": "what type of product is this (e.g. bottle, box, app screenshot, clothing)",
  "product_description": "detailed visual description of the product",
  "key_features": ["feature1", "feature2", "feature3"],
  "style": "the visual style of the product (premium, casual, artisan, tech, etc)",
  "best_angles": "what angles or compositions would showcase this product best",
  "ideal_settings": ["setting1", "setting2", "setting3", "setting4", "setting5"],
  "photography_style": "what photography style suits this product (flat lay, lifestyle, close-up, etc)",
  "is_physical": true,
  "is_digital": false
}"""


def _strip_b64_prefix(b64: str) -> tuple[str, str]:
    """Remove ``data:…;base64,`` prefix if present.

    Returns:
        (raw_base64, format) where format is "png", "jpeg", "gif", or "webp".
    """
    # Strip data-URL prefix if present
    raw = b64
    if b64.startswith("data:"):
        raw = b64.split(",", 1)[1]

    # Always detect format from actual bytes (the prefix can lie)
    fmt = _detect_format_from_bytes(raw)
    return raw, fmt


def _detect_format_from_bytes(raw_b64: str) -> str:
    """Detect image format by decoding the first bytes and checking magic numbers."""
    try:
        # base64 needs at least 4 chars to decode; grab a safe chunk
        head = base64.b64decode(raw_b64[:64])
        if head[:3] == b"\xff\xd8\xff":
            return "jpeg"
        if head[:4] == b"\x89PNG":
            return "png"
        if head[:4] == b"GIF8":
            return "gif"
        if head[:4] == b"RIFF" and len(head) >= 12 and head[8:12] == b"WEBP":
            return "webp"
    except Exception as exc:
        logger.warning("format_detection_failed", error=str(exc))

    # Last resort default
    return "png"


def _parse_json_text(text: str) -> dict:
    """Extract a JSON object from LLM output that may contain markdown fences."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise ValueError("Vision model did not return valid JSON")


def _invoke_vision(image_b64: str, image_format: str, prompt: str) -> dict:
    """Synchronous Bedrock call with an image — meant for ``asyncio.to_thread``."""
    client = _get_bedrock_client()

    body = json.dumps({
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": image_format,
                            "source": {"bytes": image_b64},
                        },
                    },
                    {"text": prompt},
                ],
            },
        ],
        "inferenceConfig": {
            "maxTokens": 1000,
            "temperature": 0.3,
        },
    })

    response = client.invoke_model(
        modelId=VISION_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    result = json.loads(response["body"].read())
    text = result["output"]["message"]["content"][0]["text"]
    return _parse_json_text(text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def analyze_logo(logo_b64: str) -> dict:
    """Analyze a logo image with Nova Pro vision.

    Returns a dict with brand personality, style, mood, suggested scenes, etc.
    """
    raw, fmt = _strip_b64_prefix(logo_b64)
    logger.info("vision_analyze_logo", format=fmt)
    result = await asyncio.to_thread(_invoke_vision, raw, fmt, _LOGO_PROMPT)
    logger.info("vision_logo_done", keys=list(result.keys()))
    return result


async def analyze_product(product_b64: str) -> dict:
    """Analyze a product image with Nova Pro vision.

    Returns a dict with product type, features, ideal settings, etc.
    """
    raw, fmt = _strip_b64_prefix(product_b64)
    logger.info("vision_analyze_product", format=fmt)
    result = await asyncio.to_thread(_invoke_vision, raw, fmt, _PRODUCT_PROMPT)
    logger.info("vision_product_done", keys=list(result.keys()))
    return result
