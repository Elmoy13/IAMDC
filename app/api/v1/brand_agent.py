"""Brand Agent API endpoints — chat, upload, image search."""
import base64
import os
import uuid

from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException

from app.core.logging import get_logger
from app.middleware.auth import get_current_user, get_user_agency
from app.schemas.brand_agent import (
    AgentChatRequest,
    AgentChatResponse,
    FileUploadResponse,
    ImageSearchRequest,
    ImageSearchResponse,
    ImageSearchResult,
)
from app.services.brand_agent import chat as agent_chat
from app.services.image_search_service import search_images

logger = get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["brand-agent"])

# In-memory conversation history store (per session_id)
_sessions: dict[str, list[dict]] = {}


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat_endpoint(
    req: AgentChatRequest,
    agency: dict = Depends(get_user_agency),
):
    """Send a message to the Brand Strategy Agent."""
    if req.history:
        history = [{"role": m.role, "content": m.content} for m in req.history]
    else:
        history = _sessions.get(req.session_id, [])

    result = await agent_chat(
        session_id=req.session_id,
        user_message=req.message,
        history=history,
        logo_url=req.logo_url,
        uploaded_images=req.uploaded_images,
    )

    # Store updated history
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": result["reply"]})
    _sessions[req.session_id] = history

    return AgentChatResponse(
        session_id=req.session_id,
        reply=result["reply"],
        presentation=result["presentation"],
        status=result["status"],
        extracted_config=result.get("extracted_config"),
        meta=result.get("meta"),
        creative_dna=result.get("creative_dna"),
    )


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Query("default"),
    tag: str = Query("general", pattern="^(general|logo|product_image)$"),
    agency: dict = Depends(get_user_agency),
):
    """Upload a logo or image file to Supabase Storage.

    Use ``tag=product_image`` for product showcase images,
    ``tag=logo`` for logos, or ``tag=general`` (default) for anything else.
    Returns an absolute public URL usable in presentations.
    """
    ext = os.path.splitext(file.filename or "file.png")[1].lower()
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed. Use: {', '.join(allowed)}")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB.")

    # Upload to Supabase brand-assets bucket
    agency_id = agency["agency_id"]
    file_b64 = base64.b64encode(contents).decode()
    # Re-use storage_helper but with a brief-uploads path
    from app.services.supabase_client import get_client
    from datetime import datetime

    timestamp = int(datetime.now().timestamp())
    filename = f"{uuid.uuid4().hex}{ext}"
    subfolder = "product-showcase" if tag == "product_image" else "brief-uploads"
    storage_path = f"{agency_id}/{subfolder}/{session_id}/{filename}"

    client = get_client()
    content_type = f"image/{ext.lstrip('.')}"
    if ext == ".svg":
        content_type = "image/svg+xml"

    client.storage.from_("brand-assets").upload(
        path=storage_path,
        file=contents,
        file_options={"content-type": content_type, "upsert": "true"},
    )

    public_url = client.storage.from_("brand-assets").get_public_url(storage_path)
    logger.info("agent_file_uploaded", path=storage_path)

    return FileUploadResponse(url=public_url, filename=file.filename or filename)


@router.post("/search-images", response_model=ImageSearchResponse)
async def search_images_endpoint(
    req: ImageSearchRequest,
    _user: dict = Depends(get_current_user),
):
    """Search free stock images (Unsplash/Pexels) for use in presentations."""
    results = await search_images(req.query, req.count, req.orientation)
    return ImageSearchResponse(
        results=[ImageSearchResult(**r) for r in results]
    )


@router.delete("/session/{session_id}")
async def clear_session(
    session_id: str,
    _user: dict = Depends(get_current_user),
):
    """Clear a conversation session."""
    _sessions.pop(session_id, None)
    return {"status": "cleared"}
