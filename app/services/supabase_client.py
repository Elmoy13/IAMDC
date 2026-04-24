"""Supabase client for async job-based post generation.

Manages generation_jobs and generated_posts tables, plus image uploads
to the post-images storage bucket.
"""

import base64

from supabase import create_client, Client

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: Client | None = None


def get_client() -> Client:
    """Lazy-initialise and return the Supabase client."""
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

async def create_job(
    total_posts: int,
    brand_name: str,
    campaign_description: str,
    language: str = "es",
    agency_id: str | None = None,
    draft_id: str | None = None,
    config: dict | None = None,
) -> str:
    """Create a generation job and return its ID."""
    client = get_client()
    row: dict = {
        "total_posts": total_posts,
        "brand_name": brand_name,
        "campaign_description": campaign_description,
        "status": "processing",
        "language": language,
    }
    if agency_id:
        row["agency_id"] = agency_id
    if draft_id:
        row["draft_id"] = draft_id
    if config:
        row["config"] = config
    result = client.table("generation_jobs").insert(row).execute()
    job_id = result.data[0]["id"]
    logger.info("job_created", job_id=job_id, total_posts=total_posts)
    return job_id


async def update_job_progress(job_id: str, completed: int) -> None:
    """Increment the completed_posts counter on a job."""
    client = get_client()
    client.table("generation_jobs").update({
        "completed_posts": completed,
    }).eq("id", job_id).execute()


async def complete_job(job_id: str) -> None:
    """Mark a job as completed and update linked draft if any."""
    client = get_client()
    client.table("generation_jobs").update({
        "status": "completed",
    }).eq("id", job_id).execute()

    # Update linked draft status
    job = client.table("generation_jobs").select("draft_id").eq("id", job_id).maybe_single().execute()
    if job.data and job.data.get("draft_id"):
        client.table("parrilla_drafts").update({
            "status": "generated",
        }).eq("id", job.data["draft_id"]).execute()

    logger.info("job_completed", job_id=job_id)


async def fail_job(job_id: str, error: str) -> None:
    """Mark a job as failed."""
    client = get_client()
    client.table("generation_jobs").update({
        "status": "failed",
        "error_message": error,
    }).eq("id", job_id).execute()
    logger.error("job_failed", job_id=job_id, error=error)


async def get_job_status(job_id: str, agency_id: str | None = None) -> dict:
    """Return the job row plus all its posts ordered by index."""
    client = get_client()
    query = client.table("generation_jobs").select("*").eq("id", job_id)
    if agency_id:
        query = query.eq("agency_id", agency_id)
    job = query.single().execute()
    posts = (
        client.table("generated_posts")
        .select("*")
        .eq("job_id", job_id)
        .order("index")
        .execute()
    )
    return {"job": job.data, "posts": posts.data}


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

async def create_post_placeholder(
    job_id: str, index: int, platform: str, format: str,
) -> str:
    """Create a placeholder row for a post that will be generated."""
    client = get_client()
    result = (
        client.table("generated_posts")
        .insert({
            "job_id": job_id,
            "index": index,
            "platform": platform,
            "format": format,
            "status": "generating",
        })
        .execute()
    )
    return result.data[0]["id"]


async def update_post_success(
    post_id: str,
    headline: str,
    body: str,
    cta: str,
    image_prompt: str,
    image_url: str,
) -> None:
    """Mark a post as successfully generated."""
    client = get_client()
    client.table("generated_posts").update({
        "status": "success",
        "headline": headline,
        "body": body,
        "cta": cta,
        "image_prompt": image_prompt,
        "rendered_image_url": image_url,
    }).eq("id", post_id).execute()


async def update_post_error(post_id: str, error: str) -> None:
    """Mark a post as failed."""
    client = get_client()
    client.table("generated_posts").update({
        "status": "error",
        "error_message": error,
    }).eq("id", post_id).execute()


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

async def get_post(post_id: str) -> dict | None:
    """Fetch a single post by ID."""
    client = get_client()
    result = (
        client.table("generated_posts")
        .select("*")
        .eq("id", post_id)
        .single()
        .execute()
    )
    return result.data


async def update_post_video(
    post_id: str,
    video_url: str,
    motion_prompt: str,
) -> None:
    """Set the video URL and motion prompt on a post."""
    client = get_client()
    client.table("generated_posts").update({
        "video_url": video_url,
        "video_status": "success",
        "motion_prompt": motion_prompt,
    }).eq("id", post_id).execute()


async def update_post_video_status(post_id: str, status: str, error: str = "") -> None:
    """Update only the video_status (and optionally video_error) on a post."""
    client = get_client()
    update: dict = {"video_status": status}
    if error:
        update["video_error"] = error
    client.table("generated_posts").update(update).eq("id", post_id).execute()


async def upload_video_to_storage(video_bytes: bytes, filename: str) -> str:
    """Upload video bytes to the post-images bucket and return its public URL."""
    client = get_client()
    client.storage.from_("post-images").upload(
        filename,
        video_bytes,
        file_options={"content-type": "video/mp4"},
    )
    url = client.storage.from_("post-images").get_public_url(filename)
    logger.info("video_uploaded_to_supabase", filename=filename)
    return url


async def upload_image_to_storage(image_b64: str, filename: str) -> str:
    """Upload a base64 image to the post-images bucket and return its public URL."""
    client = get_client()

    # Strip data-URL prefix if present
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    image_bytes = base64.b64decode(image_b64)

    client.storage.from_("post-images").upload(
        filename,
        image_bytes,
        file_options={"content-type": "image/png"},
    )

    url = client.storage.from_("post-images").get_public_url(filename)
    logger.info("image_uploaded_to_supabase", filename=filename)
    return url


# ---------------------------------------------------------------------------
# Post versions
# ---------------------------------------------------------------------------

async def create_post_version(
    post_id: str,
    version_number: int,
    headline: str = "",
    body: str = "",
    cta: str = "",
    image_prompt: str = "",
    rendered_image_url: str = "",
    base_image_url: str = "",
    user_message: str = "",
    ai_response: str = "",
    change_scope: str = "",
) -> str:
    """Create a new post version and mark previous ones as not current."""
    client = get_client()

    # Mark all existing versions for this post as not current
    client.table("post_versions").update({
        "is_current": False,
    }).eq("post_id", post_id).execute()

    result = (
        client.table("post_versions")
        .insert({
            "post_id": post_id,
            "version_number": version_number,
            "headline": headline,
            "body": body,
            "cta": cta,
            "image_prompt": image_prompt,
            "rendered_image_url": rendered_image_url,
            "base_image_url": base_image_url,
            "user_message": user_message,
            "ai_response": ai_response,
            "change_scope": change_scope,
            "is_current": True,
        })
        .execute()
    )
    version_id = result.data[0]["id"]

    # Update the post's version counter
    client.table("generated_posts").update({
        "current_version_number": version_number,
    }).eq("id", post_id).execute()

    logger.info("post_version_created", post_id=post_id, version=version_number)
    return version_id


async def get_post_versions(post_id: str) -> list[dict]:
    """Return all versions of a post, newest first."""
    client = get_client()
    result = (
        client.table("post_versions")
        .select("*")
        .eq("post_id", post_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


async def get_post_version(version_id: str) -> dict | None:
    """Fetch a single version by ID."""
    client = get_client()
    result = (
        client.table("post_versions")
        .select("*")
        .eq("id", version_id)
        .single()
        .execute()
    )
    return result.data


async def restore_post_version(post_id: str, version_id: str) -> dict:
    """Restore a specific version: mark it current and update the post."""
    client = get_client()

    # Mark all versions as not current
    client.table("post_versions").update({
        "is_current": False,
    }).eq("post_id", post_id).execute()

    # Mark the target version as current
    client.table("post_versions").update({
        "is_current": True,
    }).eq("id", version_id).execute()

    # Fetch the version data
    version = await get_post_version(version_id)

    # Update the post with the version's data
    client.table("generated_posts").update({
        "headline": version["headline"],
        "body": version["body"],
        "cta": version["cta"],
        "image_prompt": version["image_prompt"],
        "rendered_image_url": version["rendered_image_url"],
        "base_image_url": version.get("base_image_url", ""),
        "current_version_number": version["version_number"],
        "edit_status": "idle",
    }).eq("id", post_id).execute()

    logger.info("post_version_restored", post_id=post_id, version=version["version_number"])
    return version


# ---------------------------------------------------------------------------
# Post edit chat
# ---------------------------------------------------------------------------

async def add_edit_chat_message(
    post_id: str,
    role: str,
    content: str,
    version_id: str | None = None,
) -> str:
    """Add a message to the edit chat history."""
    client = get_client()
    row: dict = {
        "post_id": post_id,
        "role": role,
        "content": content,
    }
    if version_id:
        row["version_id"] = version_id
    result = client.table("post_edit_chat").insert(row).execute()
    return result.data[0]["id"]


async def get_edit_chat_history(post_id: str) -> list[dict]:
    """Return the full edit chat history for a post."""
    client = get_client()
    result = (
        client.table("post_edit_chat")
        .select("*")
        .eq("post_id", post_id)
        .order("created_at")
        .execute()
    )
    return result.data


async def update_post_edit_status(post_id: str, edit_status: str) -> None:
    """Update the edit_status field on a post."""
    client = get_client()
    client.table("generated_posts").update({
        "edit_status": edit_status,
    }).eq("id", post_id).execute()


async def update_post_fields(post_id: str, fields: dict) -> None:
    """Update arbitrary fields on a generated_posts row."""
    client = get_client()
    client.table("generated_posts").update(fields).eq("id", post_id).execute()


async def update_post_copy_success(
    post_id: str,
    headline: str,
    body: str,
    cta: str,
    image_prompt: str,
) -> None:
    """Mark a post as copy-generated (no image yet)."""
    client = get_client()
    client.table("generated_posts").update({
        "status": "success",
        "image_status": "pending",
        "headline": headline,
        "body": body,
        "cta": cta,
        "image_prompt": image_prompt,
    }).eq("id", post_id).execute()


async def list_posts_by_job(job_id: str, filters: dict | None = None) -> list[dict]:
    """Return all posts for a job, optionally filtered by column values."""
    client = get_client()
    query = (
        client.table("generated_posts")
        .select("*")
        .eq("job_id", job_id)
    )
    if filters:
        for col, val in filters.items():
            query = query.eq(col, val)
    result = query.order("index").execute()
    return result.data


async def get_job(job_id: str) -> dict | None:
    """Fetch a single job by ID."""
    client = get_client()
    result = (
        client.table("generation_jobs")
        .select("*")
        .eq("id", job_id)
        .single()
        .execute()
    )
    return result.data


async def get_draft(draft_id: str) -> dict | None:
    """Fetch a single draft by ID."""
    client = get_client()
    result = (
        client.table("parrilla_drafts")
        .select("*")
        .eq("id", draft_id)
        .execute()
    )
    if result.data:
        return result.data[0]
    return None


async def list_jobs_by_draft(draft_id: str) -> list[dict]:
    """Return all generation jobs linked to a draft, newest first."""
    client = get_client()
    result = (
        client.table("generation_jobs")
        .select("*")
        .eq("draft_id", draft_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


async def list_posts_by_job_ids(job_ids: list[str]) -> list[dict]:
    """Return all posts for multiple jobs, ordered by created_at ASC."""
    if not job_ids:
        return []
    client = get_client()
    result = (
        client.table("generated_posts")
        .select("*")
        .in_("job_id", job_ids)
        .order("created_at")
        .execute()
    )
    return result.data


async def update_draft_status(draft_id: str, new_status: str) -> None:
    """Update the status field on a parrilla_drafts row."""
    client = get_client()
    client.table("parrilla_drafts").update({
        "status": new_status,
    }).eq("id", draft_id).execute()
