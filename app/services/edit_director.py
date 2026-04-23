"""Edit Director — analyzes user feedback and decides what to regenerate.

Uses Nova Pro with VISION to look at the current post image, understand
the user's edit request, and produce a structured EditDecision with the
exact change_scope and new prompts needed.
"""

import asyncio
import base64
import json

import httpx

from app.config import settings
from app.core.logging import get_logger
from app.services.template_generator import _get_bedrock_client

logger = get_logger(__name__)

QUICK_ACTIONS: dict[str, str] = {
    "more_vibrant": "Haz los colores más vibrantes y saturados, más energía visual",
    "different_angle": "Prueba otro ángulo de cámara completamente diferente",
    "more_minimalist": "Estilo más minimalista y limpio, menos elementos, más espacio negativo",
    "change_background": "Cambia el fondo por algo distinto pero coherente con la marca",
    "more_editorial": "Estilo editorial de revista, más sofisticado y artístico",
    "better_lighting": "Mejora la iluminación, hazla más cinematográfica y dramática",
    "closer_shot": "Toma más cercana al producto, close-up con bokeh",
    "change_typography": "Cambia el estilo de la tipografía, prueba algo diferente",
}

EDIT_DIRECTOR_SYSTEM = """\
You are an expert creative director for digital advertising.
You analyze a current marketing post image and the user's feedback to decide exactly what to change.

Your job:
1. Understand WHAT the user wants to change (image? text? logo? everything?)
2. Translate their feedback into specific technical instructions
3. Generate a professional prompt for image models (Flux/Nano Banana)
4. Respond to the user in {language_full} confirming what you'll do

CLASSIFICATION RULES:
- "change headline/text/copy/body/cta" → change_scope = "copy_only" (NO image regen)
- "bigger text/smaller text/different font/typography" → "text_overlay" (Nano Banana 2 only)
- "bigger logo/move logo/different position" → "logo_overlay" (Nano Banana 2 only)
- "change background/lighting/angle/style/scene/bottle/product placement" → "base_image" (Flux + overlays)
- "redo everything/start over/completely different" → "full"

For new_image_prompt:
- ALWAYS write in English (image models prefer it)
- Include: style, lighting, composition, focus, mood
- End with: "absolutely no text, no words, no letters in the image"
- Be ultra specific (not "modern and nice" but "editorial fashion photography, 85mm lens, golden hour light, shallow depth of field")
- Start with "This product" so Flux knows the reference

Respond with VALID JSON only. Schema:
{{
  "change_scope": "base_image" | "text_overlay" | "logo_overlay" | "full" | "copy_only",
  "reasoning": "Internal reasoning (1-2 sentences)",
  "ai_response_to_user": "Friendly confirmation in {language_full} (2-3 sentences max)",
  "new_image_prompt": "..." or null,
  "new_headline": "..." or null,
  "new_body": "..." or null,
  "new_cta": "..." or null,
  "text_style_instruction": "..." or null
}}"""


async def analyze_edit_request(
    post: dict,
    brand_context: dict | None,
    campaign_brief: str,
    user_message: str,
    chat_history: list[dict],
    current_image_url: str,
    language: str = "es",
) -> dict:
    """Analyze the user's edit request with Nova Pro Vision.

    Returns an EditDecision dict with change_scope and new prompts.
    """
    language_full = "español" if language == "es" else "English"

    system = EDIT_DIRECTOR_SYSTEM.format(language_full=language_full)

    # Build context for the user prompt
    brand_info = json.dumps(brand_context, ensure_ascii=False) if brand_context else "N/A"
    recent_chat = ""
    if chat_history:
        last_msgs = chat_history[-6:]
        recent_chat = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in last_msgs
        )

    user_prompt = (
        f"CURRENT POST:\n"
        f"- Headline: {post.get('headline', '')}\n"
        f"- Body: {post.get('body', '')}\n"
        f"- CTA: {post.get('cta', '')}\n"
        f"- Previous image prompt: {post.get('image_prompt', '')}\n\n"
        f"BRAND CONTEXT: {brand_info}\n"
        f"CAMPAIGN: {campaign_brief}\n\n"
        f"RECENT CHAT:\n{recent_chat}\n\n"
        f"USER REQUEST: {user_message}\n\n"
        f"Analyze the current image and the user's request. Respond with JSON."
    )

    # Download the current image for vision
    image_b64 = ""
    if current_image_url:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(current_image_url)
                resp.raise_for_status()
                image_b64 = base64.b64encode(resp.content).decode("utf-8")
        except Exception as exc:
            logger.warning("edit_director_image_download_failed", error=str(exc))

    def _call():
        bedrock = _get_bedrock_client()

        # Build content: image (if available) + text
        content = []
        if image_b64:
            content.append({
                "image": {
                    "format": "png",
                    "source": {"bytes": image_b64},
                }
            })
        content.append({"text": user_prompt})

        body = json.dumps({
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": content}],
            "inferenceConfig": {"maxTokens": 1024, "temperature": 0.7},
        })
        resp = bedrock.invoke_model(
            modelId="amazon.nova-pro-v1:0",
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        result = json.loads(resp["body"].read())
        return result["output"]["message"]["content"][0]["text"]

    raw = await asyncio.to_thread(_call)
    logger.debug("edit_director_raw", response=raw[:200])

    # Parse JSON from response
    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        decision = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            decision = json.loads(text[start:end])
        else:
            raise ValueError(f"Edit director did not return valid JSON: {raw[:300]}")

    # Validate change_scope
    valid_scopes = {"base_image", "text_overlay", "logo_overlay", "full", "copy_only"}
    if decision.get("change_scope") not in valid_scopes:
        decision["change_scope"] = "base_image"

    return decision
