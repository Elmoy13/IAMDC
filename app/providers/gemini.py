import httpx

from app.config import settings
from app.core.exceptions import AIProviderError
from app.core.logging import get_logger

logger = get_logger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _build_contents(system_prompt: str, user_message: str, history: list[dict]) -> list[dict]:
    """Build Gemini-formatted contents array from history + new message."""
    contents: list[dict] = []

    # System instruction is sent as a separate role in Gemini
    # History: each dict has {"role": "user"|"model", "content": "..."}
    for msg in history:
        role = "model" if msg["role"] in ("agent", "ai", "model") else "user"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    contents.append({"role": "user", "parts": [{"text": user_message}]})
    return contents


async def generate_response(
    system_prompt: str,
    user_message: str,
    history: list[dict],
) -> str:
    """Call Google Gemini to generate a chat response."""
    url = GEMINI_API_URL.format(model=settings.gemini_model)
    params = {"key": settings.gemini_api_key}

    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": _build_contents(system_prompt, user_message, history),
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
        },
    }

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, json=body, params=params)

    if response.status_code != 200:
        logger.error("gemini_error", status=response.status_code, body=response.text[:200] if response.text else None)
        raise AIProviderError(detail=f"Gemini error {response.status_code}")

    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        logger.error("gemini_parse_error", data=data)
        raise AIProviderError(detail="Failed to parse Gemini response") from exc
