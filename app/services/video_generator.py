"""Kling video generation via fal.ai queue API.

Generates short product videos from static post images using Kling v2.5
turbo/pro image-to-video. Uses Nova Pro to create motion prompts that
describe subtle, professional camera and product movements.
"""

import asyncio
import base64
import json

import httpx

from app.config import settings
from app.core.logging import get_logger
from app.services.template_generator import _get_bedrock_client

logger = get_logger(__name__)

FAL_KLING_URL = "https://queue.fal.run/fal-ai/kling-video/v2.5-turbo/pro/image-to-video"

VISION_MOTION_PROMPT = """You are a cinematic director. Analyze this image and create a motion prompt for a 5-second video animation.

STEP 1 - Describe what you see:
- Main subject (product, person, object)
- Background elements
- Lighting conditions
- Composition (close-up, wide, flat lay, etc.)

STEP 2 - Based on what you see, create a CINEMATIC motion prompt that:
- Starts with a camera movement (dolly, zoom, pan, orbit, crane, tilt)
- Adds subtle environmental motion (steam, light flicker, liquid movement, hair, fabric)
- Creates emotional impact (dramatic reveal, intimate approach, energetic sweep)
- Keeps the main product SHARP and IN FOCUS throughout

RULES:
- Maximum 40 words for the final motion prompt
- Write in English
- Be SPECIFIC to what's actually in this image
- The product must stay recognizable — no extreme warping
- Prefer SLOW, ELEGANT movements over fast/chaotic ones

RESPOND WITH ONLY THE MOTION PROMPT. Nothing else. No explanation, no steps, no analysis. Just the motion prompt."""


async def generate_motion_prompt(image_url: str) -> str:
    """Analyze the generated image with Nova Pro VISION and create
    a cinematic motion prompt specific to what's actually in the image."""

    # Download the image to send to Nova Pro
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(image_url)
        resp.raise_for_status()
        image_bytes = resp.content

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    def _call():
        bedrock = _get_bedrock_client()
        body = json.dumps({
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": "png",
                                "source": {"bytes": image_b64},
                            }
                        },
                        {"text": VISION_MOTION_PROMPT},
                    ],
                }
            ],
            "inferenceConfig": {"maxTokens": 80, "temperature": 0.7},
        })
        resp = bedrock.invoke_model(
            modelId="amazon.nova-pro-v1:0",
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        result = json.loads(resp["body"].read())
        motion = result["output"]["message"]["content"][0]["text"].strip()

        # Clean up if Nova Pro added extra prefixes
        for prefix in ["Motion prompt:", "Prompt:", "Here is", "The motion"]:
            if motion.lower().startswith(prefix.lower()):
                motion = motion[len(prefix):].strip()

        return motion.strip('"')

    motion = await asyncio.to_thread(_call)
    logger.info("motion_prompt_generated", motion=motion[:80])
    return motion


async def submit_video_job(
    image_url: str,
    prompt: str,
    duration: str = "5",
    aspect_ratio: str = "9:16",
) -> dict:
    """Submit a video generation job to fal.ai Kling queue.

    Returns the queue response containing request_id and status_url.
    """
    headers = {
        "Authorization": f"Key {settings.fal_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": prompt,
        "image_url": image_url,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        logger.info("kling_submit", prompt=prompt[:80], duration=duration)
        response = await client.post(FAL_KLING_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        logger.info(
            "kling_queued",
            request_id=data.get("request_id"),
            status_url=data.get("status_url", "")[:120],
            response_url=data.get("response_url", "")[:120],
        )
        return data


async def _poll_url(url: str) -> dict:
    """GET a fal.ai URL with auth headers."""
    headers = {"Authorization": f"Key {settings.fal_key}"}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def download_video_bytes(video_url: str) -> bytes:
    """Download a video from a URL and return raw bytes."""
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(video_url)
        response.raise_for_status()
        return response.content


async def generate_video(
    image_url: str,
    prompt: str,
    duration: str = "5",
    aspect_ratio: str = "9:16",
    max_polls: int = 90,
    poll_interval: float = 3.0,
) -> str:
    """End-to-end: submit job, poll until done, return video URL.

    Uses the status_url and response_url returned by fal.ai's queue API
    instead of constructing them manually.
    """
    queue_resp = await submit_video_job(image_url, prompt, duration, aspect_ratio)
    request_id = queue_resp.get("request_id", "unknown")
    status_url = queue_resp.get("status_url")
    response_url = queue_resp.get("response_url")

    if not status_url or not response_url:
        # If the response already contains the video (sync completion)
        video_url = queue_resp.get("video", {}).get("url")
        if video_url:
            return video_url
        raise RuntimeError(
            f"Kling queue response missing status_url/response_url: {str(queue_resp)[:500]}"
        )

    for _ in range(max_polls):
        status_resp = await _poll_url(status_url)
        status = status_resp.get("status")
        logger.info("kling_poll", request_id=request_id, status=status)

        if status == "COMPLETED":
            result = await _poll_url(response_url)
            video_url = result.get("video", {}).get("url")
            if not video_url:
                raise RuntimeError(
                    f"Kling completed but no video URL. Response: {str(result)[:500]}"
                )
            logger.info("kling_completed", request_id=request_id, video_url=video_url[:80])
            return video_url

        if status in ("FAILED", "CANCELLED"):
            raise RuntimeError(
                f"Kling video generation {status}. Response: {str(status_resp)[:500]}"
            )

        await asyncio.sleep(poll_interval)

    raise TimeoutError(
        f"Kling video generation timed out after {max_polls * poll_interval}s "
        f"(request_id={request_id})"
    )
