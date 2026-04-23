"""Free image search using Unsplash and Pexels APIs."""
import httpx

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

UNSPLASH_BASE = "https://api.unsplash.com/search/photos"
PEXELS_BASE = "https://api.pexels.com/v1/search"


async def search_images(query: str, count: int = 5, orientation: str = "landscape") -> list[dict]:
    """Search for free stock images. Tries Unsplash first, falls back to Pexels."""
    images = await _search_unsplash(query, count, orientation)
    if not images:
        images = await _search_pexels(query, count, orientation)
    return images


async def _search_unsplash(query: str, count: int, orientation: str) -> list[dict]:
    if not settings.unsplash_access_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                UNSPLASH_BASE,
                params={
                    "query": query,
                    "per_page": count,
                    "orientation": orientation,
                },
                headers={"Authorization": f"Client-ID {settings.unsplash_access_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "url": r["urls"]["regular"],
                    "thumb": r["urls"]["thumb"],
                    "alt": r["alt_description"] or query,
                    "credit": f'Photo by {r["user"]["name"]} on Unsplash',
                    "width": r["width"],
                    "height": r["height"],
                }
                for r in data.get("results", [])
            ]
    except Exception as exc:
        logger.warning("unsplash_search_error", error=str(exc))
        return []


async def _search_pexels(query: str, count: int, orientation: str) -> list[dict]:
    if not settings.pexels_api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                PEXELS_BASE,
                params={
                    "query": query,
                    "per_page": count,
                    "orientation": orientation,
                },
                headers={"Authorization": settings.pexels_api_key},
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "url": p["src"]["large2x"],
                    "thumb": p["src"]["medium"],
                    "alt": p.get("alt") or query,
                    "credit": f'Photo by {p["photographer"]} on Pexels',
                    "width": p["width"],
                    "height": p["height"],
                }
                for p in data.get("photos", [])
            ]
    except Exception as exc:
        logger.warning("pexels_search_error", error=str(exc))
        return []
