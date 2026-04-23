"""Serve temporary images uploaded for Flux Kontext reference."""

import os
import re

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

router = APIRouter(tags=["temp-files"])

TEMP_IMAGES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "temp_images"
)

_SAFE_FILENAME = re.compile(r"^[0-9a-f\-]{36}\.png$")


@router.get("/temp-images/{filename}")
async def serve_temp_image(filename: str):
    """Serve a temporary product image by filename."""
    if not _SAFE_FILENAME.match(filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    filepath = os.path.join(TEMP_IMAGES_DIR, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    return FileResponse(filepath, media_type="image/png")
