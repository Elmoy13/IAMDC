"""JWT authentication and multi-tenancy dependencies.

Validates Supabase JWTs (ES256 via JWKS), extracts user identity,
and resolves the user's agency for row-level access control.
"""

from functools import lru_cache
from typing import Optional

import jwt
from jwt import PyJWKClient
from fastapi import Depends, Header, HTTPException
from supabase import Client, create_client

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── JWKS client (cached, with built-in key caching) ──────

_JWKS_URL = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"


@lru_cache(maxsize=1)
def _get_jwks_client() -> PyJWKClient:
    return PyJWKClient(_JWKS_URL, cache_keys=True, lifespan=3600)


async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> dict:
    """Extract and validate the JWT. Returns user info dict.

    Use as a FastAPI dependency on any protected endpoint.
    Supports both ES256 (JWKS) and HS256 (legacy shared secret).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = authorization[7:]  # strip "Bearer "

    try:
        # Peek at header to detect algorithm
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "")

        if alg == "HS256" and settings.supabase_jwt_secret:
            # Legacy: shared-secret validation
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            # JWKS-based validation (ES256, RS256, etc.)
            jwks_client = _get_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg or "ES256"],
                audience="authenticated",
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as exc:
        logger.warning("jwt_validation_failed", alg=alg, error=str(exc))
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub")

    return {
        "user_id": user_id,
        "email": payload.get("email"),
        "jwt_token": token,
        "jwt_alg": alg or "unknown",
    }


def get_user_supabase_client(
    user: dict = Depends(get_current_user),
) -> Client:
    """Return a Supabase client authenticated with the user's JWT.

    Queries made with this client respect RLS policies automatically.
    """
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(user["jwt_token"])
    return client


async def get_user_agency(
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_user_supabase_client),
) -> dict:
    """Resolve the user's agency. Returns agency context dict.

    For MVP we assume 1 user = 1 agency (first membership).
    """
    result = (
        supabase.table("agency_members")
        .select("agency_id, role, agencies(id, name)")
        .eq("user_id", user["user_id"])
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=403, detail="User has no agency")

    member = result.data[0]
    return {
        "agency_id": member["agency_id"],
        "agency_name": member["agencies"]["name"],
        "role": member["role"],
        "user_id": user["user_id"],
        "jwt_token": user["jwt_token"],
    }
