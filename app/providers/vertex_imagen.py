import json
import time

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from app.config import settings
from app.core.exceptions import ImageGenerationError
from app.core.logging import get_logger

logger = get_logger(__name__)

IMAGEN_URL = (
    "https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}"
    "/publishers/google/models/imagen-3.0-generate-002:predict"
)

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

_cached_credentials: service_account.Credentials | None = None


def _get_access_token() -> str:
    """Obtain a fresh access token from the GCP service account."""
    global _cached_credentials

    if _cached_credentials is None or not _cached_credentials.valid:
        sa_info = json.loads(settings.gcp_service_account_json)
        _cached_credentials = service_account.Credentials.from_service_account_info(
            sa_info, scopes=SCOPES
        )

    if not _cached_credentials.valid:
        _cached_credentials.refresh(GoogleAuthRequest())

    return _cached_credentials.token


async def generate_image(prompt: str) -> str:
    """Generate an image using Vertex AI Imagen 3 and return base64-encoded PNG."""
    url = IMAGEN_URL.format(
        location=settings.gcp_location,
        project=settings.gcp_project_id,
    )
    access_token = _get_access_token()

    body = {
        "instances": [
            {
                "prompt": prompt,
            }
        ],
        "parameters": {
            "sampleCount": 1,
            "outputOptions": {"mimeType": "image/png"},
        },
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, json=body, headers=headers)

    if response.status_code != 200:
        logger.error(
            "vertex_imagen_error",
            status=response.status_code,
            body=response.text[:200] if response.text else None,
        )
        raise ImageGenerationError(
            detail=f"Vertex AI Imagen error {response.status_code}"
        )

    data = response.json()
    try:
        return data["predictions"][0]["bytesBase64Encoded"]
    except (KeyError, IndexError) as exc:
        logger.error("vertex_imagen_parse_error", data=data)
        raise ImageGenerationError(detail="Failed to parse Imagen response") from exc
