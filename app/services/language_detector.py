"""Language detection for content generation.

Uses Nova Pro to detect whether the brand context is Spanish or English,
so the pipeline generates copy in the correct language.
"""

import asyncio
import json

from app.core.logging import get_logger
from app.services.template_generator import _get_bedrock_client
from app.config import settings

logger = get_logger(__name__)

DETECT_PROMPT = """\
Analyze the following texts and determine the primary language.
Respond with ONLY "es" (Spanish) or "en" (English). Nothing else.

Brand name: {brand_name}
Campaign brief: {campaign_brief}
Chat messages: {chat_excerpt}"""


def _call_detect(prompt: str) -> str:
    client = _get_bedrock_client()
    body = json.dumps({
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 5, "temperature": 0.0},
    })
    resp = client.invoke_model(
        modelId=settings.template_model_id,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(resp["body"].read())
    return result["output"]["message"]["content"][0]["text"].strip().lower()


async def detect_language(
    brand_name: str = "",
    campaign_brief: str = "",
    chat_messages: list[dict] | None = None,
) -> str:
    """Detect language from brand context. Returns 'es' or 'en'.

    Defaults to 'es' if detection is inconclusive.
    """
    # Build a short excerpt from chat (last 3 user messages)
    chat_excerpt = ""
    if chat_messages:
        user_msgs = [m["content"] for m in chat_messages if m.get("role") == "user"]
        chat_excerpt = " | ".join(user_msgs[-3:])

    # If there's almost no text to analyze, default to Spanish
    total_text = f"{brand_name} {campaign_brief} {chat_excerpt}".strip()
    if len(total_text) < 5:
        return "es"

    prompt = DETECT_PROMPT.format(
        brand_name=brand_name or "(not provided)",
        campaign_brief=campaign_brief or "(not provided)",
        chat_excerpt=chat_excerpt or "(no chat)",
    )

    try:
        raw = await asyncio.to_thread(_call_detect, prompt)
        lang = raw.strip('"').strip("'")
        if lang in ("es", "en"):
            logger.info("language_detected", language=lang)
            return lang
        logger.warning("language_detection_unclear", raw=raw)
        return "es"
    except Exception as exc:
        logger.error("language_detection_failed", error=str(exc))
        return "es"
