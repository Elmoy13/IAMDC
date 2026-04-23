"""ES→EN image prompt optimizer.

Transforms Spanish image prompts into optimised English prompts for
Flux, Nano Banana, and Kling.  Uses GLM-5 via the Bedrock fallback
chain.  On failure, falls back to the original Spanish prompt so that
image generation never blocks.
"""

from app.core.logging import get_logger
from app.providers import bedrock

logger = get_logger(__name__)


async def optimize_image_prompt(
    prompt_es: str,
    brand_context: dict | None = None,
    platform: str | None = None,
    format_label: str | None = None,
) -> str:
    """Rewrite a Spanish image prompt into optimised English for AI image models.

    This is **not** a literal translation — the prompt is reinterpreted
    as a visual brief with technical photography/lighting vocabulary.

    Args:
        prompt_es: Original prompt in Spanish (user-facing).
        brand_context: ``{name, tone, primary_color, …}``
        platform: ``"instagram"`` | ``"tiktok"`` | ``"linkedin"`` etc.
        format_label: ``"instagram_feed"`` | ``"instagram_story"`` etc.

    Returns:
        Optimised English prompt (~80-150 chars).
        On error, returns *prompt_es* unchanged.
    """
    if not prompt_es or not prompt_es.strip():
        return prompt_es

    brand = brand_context or {}

    system = (
        "You are an expert prompt engineer for AI image models "
        "(Flux Pro, Nano Banana, Kling).\n\n"
        "Your job: transform Spanish prompts into optimized English prompts that "
        "produce better images.\n\n"
        "Rules:\n"
        "1. Don't translate literally. Reinterpret as a visual brief.\n"
        "2. Add technical visual vocabulary: lighting (soft, cinematic, golden "
        "hour), composition (shallow DOF, rule of thirds, centered), style "
        "(editorial photography, lifestyle, documentary), camera "
        "specs when useful (35mm, shot on film).\n"
        "3. Keep brand tone — if playful/irreverent, keep that energy in English.\n"
        "4. 1-2 sentences. Prompt quality > prompt length.\n"
        "5. Include: subject, setting, mood, style, lighting.\n"
        "6. Never mention \"Spanish\" or \"translation\" — output only the final "
        "English prompt.\n\n"
        "Output format: just the English prompt text, no quotes, no prefix."
    )

    platform_hint = ""
    if platform and "instagram" in platform:
        platform_hint = "Instagram feed aesthetic, polished but authentic. "
    elif platform and "tiktok" in platform:
        platform_hint = "TikTok vibes, dynamic energy, gen-z visual language. "
    elif platform and "linkedin" in platform:
        platform_hint = "LinkedIn professional, but human and approachable. "

    user = (
        f"Brand: {brand.get('name', 'Unknown')}\n"
        f"Brand tone: {brand.get('tone', 'professional')}\n"
        f"{platform_hint}\n"
        f"{f'Format: {format_label}. ' if format_label else ''}\n\n"
        f"Spanish prompt to optimize:\n{prompt_es}\n\n"
        f"Output only the English optimized prompt."
    )

    try:
        messages = [{"role": "user", "content": [{"text": user}]}]

        result, _model = await bedrock.invoke_with_fallback(
            system_prompt=system,
            messages=messages,
            max_tokens=200,
            temperature=0.4,
        )

        cleaned = result.strip().strip('"').strip("'").strip()

        logger.info(
            "prompt_optimized",
            original_len=len(prompt_es),
            optimized_len=len(cleaned),
        )
        return cleaned

    except Exception as exc:
        # If the optimizer fails, fall back to the original prompt
        # (a mediocre image is better than no image)
        logger.error("prompt_optimization_failed", error=str(exc)[:200])
        return prompt_es
