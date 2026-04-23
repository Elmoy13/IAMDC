"""Agency & user info endpoints."""

from fastapi import APIRouter, Depends

from app.config import settings
from app.middleware.auth import get_current_user, get_user_agency

router = APIRouter(tags=["agency"])


@router.get("/user/me")
async def get_current_user_info(
    user: dict = Depends(get_current_user),
) -> dict:
    """Return the authenticated user's basic info."""
    return {
        "user_id": user["user_id"],
        "email": user["email"],
    }


@router.get("/agency/me")
async def get_my_agency(
    agency: dict = Depends(get_user_agency),
) -> dict:
    """Return the user's agency context."""
    return {
        "agency_id": agency["agency_id"],
        "agency_name": agency["agency_name"],
        "role": agency["role"],
    }


# ── Debug endpoint (development only) ────────────────────
if settings.environment == "development":

    @router.get("/debug/whoami", include_in_schema=False)
    async def whoami(user: dict = Depends(get_current_user)) -> dict:
        """Debug: verify JWT auth is working end-to-end."""
        return {
            "user_id": user["user_id"],
            "email": user["email"],
            "jwt_alg": user.get("jwt_alg", "unknown"),
        }
