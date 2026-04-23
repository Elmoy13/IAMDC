from app.providers import bedrock
from app.core.logging import get_logger

logger = get_logger(__name__)


async def generate_response(
    system_prompt: str,
    user_message: str,
    history: list[dict],
) -> str:
    """Route AI generation to GLM-5 via Bedrock with fallback chain.

    Uses the same fallback chain as the rest of the project
    (GLM-5 → GLM-4.7 → Nova Pro).
    """
    logger.info("ai_generate", provider="bedrock_fallback")

    messages = bedrock._build_converse_messages(user_message, history)
    text, model_used = await bedrock.invoke_with_fallback(
        system_prompt=system_prompt,
        messages=messages,
        max_tokens=800,
        temperature=0.7,
    )
    logger.info("ai_generate_done", model=model_used)
    return text
