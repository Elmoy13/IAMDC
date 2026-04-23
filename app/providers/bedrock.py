"""AWS Bedrock provider — unified converse API with fallback chain.

Supports all Bedrock-compatible models (GLM, Nova, Claude, etc.) via
the standard Converse API. Falls back through a configurable chain of
models when the primary model fails.  Includes retry-with-backoff for
transient errors and a semaphore for concurrency control.
"""
import asyncio
import json
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.core.exceptions import AIProviderError
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Concurrency control ───────────────────────────────────

MAX_CONCURRENT_INVOKES = 5
_semaphore = asyncio.Semaphore(MAX_CONCURRENT_INVOKES)

# Transient error codes that justify a retry
_RETRYABLE_CODES = {"ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException"}


@lru_cache(maxsize=1)
def _get_bedrock_client():
    kwargs = {
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }
    if settings.aws_session_token:
        kwargs["aws_session_token"] = settings.aws_session_token
    return boto3.client("bedrock-runtime", **kwargs)


def _get_fallback_chain() -> list[str]:
    """Parse the comma-separated fallback chain from settings."""
    raw = settings.agent_fallback_chain
    return [m.strip() for m in raw.split(",") if m.strip()]


def _build_converse_messages(
    user_message: str, history: list[dict]
) -> list[dict]:
    """Build messages in Bedrock Converse API format."""
    messages: list[dict] = []
    for msg in history:
        role = "assistant" if msg["role"] in ("agent", "ai", "model") else "user"
        messages.append({"role": role, "content": [{"text": msg["content"]}]})
    messages.append({"role": "user", "content": [{"text": user_message}]})
    return messages


# ── Core invoke via Converse API ──────────────────────────

async def invoke(
    model_id: str,
    system_prompt: str,
    messages: list[dict],
    *,
    max_tokens: int = 8000,
    temperature: float = 0.7,
    max_retries: int = 3,
) -> str:
    """Call a single Bedrock model using the Converse API.

    Retries transient errors (throttling, timeout) with exponential backoff.
    """
    client = _get_bedrock_client()

    converse_kwargs: dict = {
        "modelId": model_id,
        "messages": messages,
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": temperature,
        },
    }

    # System prompt handling — Converse API uses a top-level `system` list
    if system_prompt:
        converse_kwargs["system"] = [{"text": system_prompt}]

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(client.converse, **converse_kwargs)
            try:
                return response["output"]["message"]["content"][0]["text"]
            except (KeyError, IndexError) as exc:
                logger.error("bedrock_parse_error", model=model_id, data=str(response)[:200])
                raise AIProviderError(
                    detail=f"Failed to parse Bedrock response from {model_id}"
                ) from exc
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            last_exc = exc
            if error_code in _RETRYABLE_CODES and attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning("bedrock_retry", model=model_id, code=error_code, attempt=attempt, wait=wait)
                await asyncio.sleep(wait)
                continue
            logger.error("bedrock_converse_error", model=model_id, code=error_code, error=str(exc))
            raise AIProviderError(
                detail=f"Bedrock {error_code} for {model_id}: {exc}"
            ) from exc
        except Exception as exc:
            logger.error("bedrock_converse_error", model=model_id, error=str(exc))
            raise AIProviderError(
                detail=f"Bedrock invoke error for {model_id}: {exc}"
            ) from exc

    # Should not reach here, but just in case
    raise AIProviderError(detail=f"Bedrock retries exhausted for {model_id}: {last_exc}")


async def invoke_bounded(
    model_id: str,
    system_prompt: str,
    messages: list[dict],
    **kwargs,
) -> str:
    """Invoke with concurrency-limited semaphore. Same args as invoke()."""
    async with _semaphore:
        return await invoke(model_id, system_prompt, messages, **kwargs)


async def invoke_with_fallback(
    system_prompt: str,
    messages: list[dict],
    *,
    max_tokens: int = 8000,
    temperature: float = 0.7,
) -> tuple[str, str]:
    """Try each model in the fallback chain until one succeeds.

    Returns:
        (generated_text, model_id_used)
    """
    chain = _get_fallback_chain()
    last_error: Exception | None = None

    for model_id in chain:
        try:
            text = await invoke(
                model_id,
                system_prompt,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if model_id != chain[0]:
                logger.warning("bedrock_fallback_used", model=model_id)
            return text, model_id
        except Exception as exc:
            logger.warning(
                "bedrock_model_failed",
                model=model_id,
                error=str(exc),
            )
            last_error = exc
            continue

    raise AIProviderError(
        detail=f"All models in fallback chain failed. Last: {last_error}"
    )


# ── Public convenience wrapper (backward-compatible) ──────

async def invoke_vision(
    model_id: str,
    system: str,
    images: list[bytes],
    user_text: str,
    *,
    max_tokens: int = 1000,
    temperature: float = 0.3,
) -> str:
    """Invoke a vision model with one or more images via the Converse API.

    Args:
        model_id: Bedrock model ID (e.g. ``us.amazon.nova-pro-v1:0``).
        system: System prompt text.
        images: List of raw image bytes (PNG/JPEG/WebP).
        user_text: User-facing text prompt.
        max_tokens: Maximum tokens for the response.
        temperature: Sampling temperature.

    Returns:
        The model's text response.
    """
    client = _get_bedrock_client()

    content_blocks: list[dict] = []
    for img_bytes in images:
        fmt = _detect_image_format(img_bytes)
        content_blocks.append({
            "image": {
                "format": fmt,
                "source": {"bytes": img_bytes},
            }
        })
    content_blocks.append({"text": user_text})

    converse_kwargs: dict = {
        "modelId": model_id,
        "system": [{"text": system}],
        "messages": [{"role": "user", "content": content_blocks}],
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": temperature,
        },
    }

    try:
        response = await asyncio.to_thread(client.converse, **converse_kwargs)
        return response["output"]["message"]["content"][0]["text"]
    except (KeyError, IndexError) as exc:
        logger.error("bedrock_vision_parse_error", model=model_id)
        raise AIProviderError(
            detail=f"Failed to parse vision response from {model_id}"
        ) from exc
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        logger.error("bedrock_vision_error", model=model_id, code=error_code)
        raise AIProviderError(
            detail=f"Bedrock vision {error_code} for {model_id}: {exc}"
        ) from exc


def _detect_image_format(img_bytes: bytes) -> str:
    """Detect image format from magic bytes. Returns 'png', 'jpeg', or 'webp'."""
    if img_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if img_bytes[:2] == b"\xff\xd8":
        return "jpeg"
    if img_bytes[:4] == b"RIFF" and img_bytes[8:12] == b"WEBP":
        return "webp"
    # Default to png
    return "png"


async def generate_response(
    system_prompt: str,
    user_message: str,
    history: list[dict],
    *,
    model_id: str | None = None,
    max_tokens: int = 4096,
) -> str:
    """High-level call: build messages and invoke a single model.

    Backward-compatible with existing callers.
    If model_id is None, uses settings.bedrock_model_id.
    """
    mid = model_id or settings.bedrock_model_id
    messages = _build_converse_messages(user_message, history)
    return await invoke(
        mid, system_prompt, messages, max_tokens=max_tokens
    )
