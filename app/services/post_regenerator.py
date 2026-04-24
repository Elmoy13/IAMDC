"""Post Regenerator — executes the regeneration based on EditDecision.

Handles the 5 change_scope modes: copy_only, text_overlay, logo_overlay,
base_image, and full. Each mode only regenerates what's needed.
"""

from app.core.logging import get_logger
from app.services import supabase_client, nano_banana
from app.services.flux_kontext import (
    generate_image_with_reference,
    download_image_as_base64,
)
from app.services.image_storage import upload_image_to_fal

logger = get_logger(__name__)


async def regenerate_post(
    post_id: str,
    edit_decision: dict,
    current_post: dict,
    brand_context: dict | None = None,
    language: str = "es",
) -> str:
    """Regenerate a post based on the edit decision.

    Returns the new version_id.
    """
    scope = edit_decision["change_scope"]
    await supabase_client.update_post_edit_status(post_id, "regenerating")

    try:
        if scope == "copy_only":
            version_id = await _regen_copy_only(post_id, edit_decision, current_post)
        elif scope == "text_overlay":
            version_id = await _regen_text_overlay(
                post_id, edit_decision, current_post, brand_context, language,
            )
        elif scope == "logo_overlay":
            version_id = await _regen_logo_overlay(
                post_id, edit_decision, current_post, brand_context, language,
            )
        elif scope == "base_image":
            version_id = await _regen_base_image(
                post_id, edit_decision, current_post, brand_context, language,
            )
        elif scope == "full":
            version_id = await _regen_full(
                post_id, edit_decision, current_post, brand_context, language,
            )
        else:
            raise ValueError(f"Unknown change_scope: {scope}")

        await supabase_client.update_post_edit_status(post_id, "idle")
        logger.info("post_regenerated", post_id=post_id, scope=scope)
        return version_id

    except Exception as exc:
        await supabase_client.update_post_edit_status(post_id, "failed")
        logger.error("post_regeneration_failed", post_id=post_id, error=str(exc))
        raise


async def _get_next_version(post_id: str) -> int:
    """Get the next version number for a post."""
    versions = await supabase_client.get_post_versions(post_id)
    if not versions:
        return 1
    return max(v["version_number"] for v in versions) + 1


async def _regen_copy_only(
    post_id: str,
    decision: dict,
    current_post: dict,
) -> str:
    """Only update headline/body/cta — no image regeneration."""
    headline = decision.get("new_headline") or current_post.get("headline", "")
    body = decision.get("new_body") or current_post.get("body", "")
    cta = decision.get("new_cta") or current_post.get("cta", "")

    # Update the post
    await supabase_client.update_post_fields(post_id, {
        "headline": headline,
        "body": body,
        "cta": cta,
    })

    # Create version (same image)
    version_number = await _get_next_version(post_id)
    version_id = await supabase_client.create_post_version(
        post_id=post_id,
        version_number=version_number,
        headline=headline,
        body=body,
        cta=cta,
        image_prompt=current_post.get("image_prompt", ""),
        rendered_image_url=current_post.get("rendered_image_url", ""),
        base_image_url=current_post.get("base_image_url", ""),
        user_message=decision.get("user_message", ""),
        ai_response=decision.get("ai_response_to_user", ""),
        change_scope="copy_only",
    )
    return version_id


async def _regen_text_overlay(
    post_id: str,
    decision: dict,
    current_post: dict,
    brand_context: dict | None,
    language: str,
) -> str:
    """Re-apply text overlay on existing base image via Nano Banana 2."""
    base_url = current_post.get("base_image_url") or current_post.get("rendered_image_url", "")
    headline = decision.get("new_headline") or current_post.get("headline", "")
    cta = decision.get("new_cta") or current_post.get("cta", "")

    colors = {}
    if brand_context:
        colors = {
            "primary_color": brand_context.get("primary_color", "#FFFFFF"),
            "secondary_color": brand_context.get("secondary_color", "#000000"),
        }

    enhanced_url = await nano_banana.enhance_post_image(
        base_image_url=base_url,
        headline=headline,
        cta=cta,
        brand_colors=colors,
        include_logo=False,
        include_text=True,
        language=language,
    )

    # Download and upload to Supabase
    image_b64 = await download_image_as_base64(enhanced_url)
    filename = f"edits/{post_id}/v{await _get_next_version(post_id)}.png"
    image_url = await supabase_client.upload_image_to_storage(image_b64, filename)

    # Update post
    await supabase_client.update_post_fields(post_id, {
        "headline": headline,
        "cta": cta,
        "rendered_image_url": image_url,
    })

    version_number = await _get_next_version(post_id)
    version_id = await supabase_client.create_post_version(
        post_id=post_id,
        version_number=version_number,
        headline=headline,
        body=current_post.get("body", ""),
        cta=cta,
        image_prompt=current_post.get("image_prompt", ""),
        rendered_image_url=image_url,
        base_image_url=base_url,
        user_message=decision.get("user_message", ""),
        ai_response=decision.get("ai_response_to_user", ""),
        change_scope="text_overlay",
    )
    return version_id


async def _regen_logo_overlay(
    post_id: str,
    decision: dict,
    current_post: dict,
    brand_context: dict | None,
    language: str,
) -> str:
    """Re-apply logo overlay on existing base image via Nano Banana 2."""
    base_url = current_post.get("base_image_url") or current_post.get("rendered_image_url", "")

    logo_url = None
    if brand_context and brand_context.get("logo_b64"):
        logo_url = await upload_image_to_fal(brand_context["logo_b64"])

    colors = {}
    if brand_context:
        colors = {
            "primary_color": brand_context.get("primary_color", "#FFFFFF"),
            "secondary_color": brand_context.get("secondary_color", "#000000"),
        }

    enhanced_url = await nano_banana.enhance_post_image(
        base_image_url=base_url,
        logo_url=logo_url,
        include_logo=True,
        include_text=False,
        brand_colors=colors,
        language=language,
    )

    image_b64 = await download_image_as_base64(enhanced_url)
    filename = f"edits/{post_id}/v{await _get_next_version(post_id)}.png"
    image_url = await supabase_client.upload_image_to_storage(image_b64, filename)

    await supabase_client.update_post_fields(post_id, {
        "rendered_image_url": image_url,
    })

    version_number = await _get_next_version(post_id)
    version_id = await supabase_client.create_post_version(
        post_id=post_id,
        version_number=version_number,
        headline=current_post.get("headline", ""),
        body=current_post.get("body", ""),
        cta=current_post.get("cta", ""),
        image_prompt=current_post.get("image_prompt", ""),
        rendered_image_url=image_url,
        base_image_url=base_url,
        user_message=decision.get("user_message", ""),
        ai_response=decision.get("ai_response_to_user", ""),
        change_scope="logo_overlay",
    )
    return version_id


async def _regen_base_image(
    post_id: str,
    decision: dict,
    current_post: dict,
    brand_context: dict | None,
    language: str,
) -> str:
    """Regenerate the base image with Flux, then re-apply overlays."""
    new_prompt = decision.get("new_image_prompt") or current_post.get("image_prompt", "")

    # Get product reference — look up from the job
    job_data = await supabase_client.get_job_status(current_post["job_id"])
    job = job_data["job"]

    # We need the product image URL — try to find from original generation
    # For now, we use the base_image_url as the reference for Flux
    # The product images are not stored per-post, so we generate without reference
    # if there's no product URL available.

    # Generate new base image with Flux
    fmt = current_post.get("format", "instagram_feed")
    aspect_map = {
        "instagram_feed": "1:1",
        "instagram_story": "9:16",
        "facebook_post": "16:9",
        "linkedin_post": "16:9",
    }
    aspect_ratio = aspect_map.get(fmt, "1:1")

    # Try to use existing base image as reference for Flux edit
    ref_url = current_post.get("base_image_url") or current_post.get("rendered_image_url", "")

    flux_image_url = await generate_image_with_reference(
        prompt=new_prompt,
        reference_image_url=ref_url,
        aspect_ratio=aspect_ratio,
    )

    # Download base image BEFORE overlays
    base_b64 = await download_image_as_base64(flux_image_url)
    base_filename = f"edits/{post_id}/base_v{await _get_next_version(post_id)}.png"
    base_url = await supabase_client.upload_image_to_storage(base_b64, base_filename)

    # Check if post had overlays — re-apply them
    final_url = base_url
    headline = decision.get("new_headline") or current_post.get("headline", "")
    body = decision.get("new_body") or current_post.get("body", "")
    cta = decision.get("new_cta") or current_post.get("cta", "")

    # If the original post had text/logo overlays, re-apply
    # We detect this by checking if base_image_url != rendered_image_url
    had_overlays = (
        current_post.get("base_image_url")
        and current_post.get("base_image_url") != current_post.get("rendered_image_url")
    )

    if had_overlays:
        logo_url = None
        if brand_context and brand_context.get("logo_b64"):
            logo_url = await upload_image_to_fal(brand_context["logo_b64"])
        elif brand_context and brand_context.get("logo_url"):
            logo_url = brand_context["logo_url"]
        else:
            # Try to resolve logo from DB via the job's draft
            job_config = job.get("config") or {}
            draft_id = job.get("draft_id")
            if draft_id:
                draft = await supabase_client.get_draft(draft_id)
                if draft and draft.get("brand_id"):
                    sc = supabase_client.get_client()
                    br = sc.table("brands").select("logo_url").eq("id", draft["brand_id"]).execute()
                    if br.data and br.data[0].get("logo_url"):
                        logo_url = br.data[0]["logo_url"]

        colors = {}
        if brand_context:
            colors = {
                "primary_color": brand_context.get("primary_color", "#FFFFFF"),
                "secondary_color": brand_context.get("secondary_color", "#000000"),
            }

        enhanced_url = await nano_banana.enhance_post_image(
            base_image_url=flux_image_url,
            logo_url=logo_url,
            headline=headline,
            cta=cta,
            brand_colors=colors,
            include_logo=bool(logo_url),
            include_text=True,
            language=language,
        )
        final_b64 = await download_image_as_base64(enhanced_url)
        final_filename = f"edits/{post_id}/v{await _get_next_version(post_id)}.png"
        final_url = await supabase_client.upload_image_to_storage(final_b64, final_filename)

    # Update post
    await supabase_client.update_post_fields(post_id, {
        "headline": headline,
        "body": body,
        "cta": cta,
        "image_prompt": new_prompt,
        "rendered_image_url": final_url,
        "base_image_url": base_url,
    })

    version_number = await _get_next_version(post_id)
    version_id = await supabase_client.create_post_version(
        post_id=post_id,
        version_number=version_number,
        headline=headline,
        body=body,
        cta=cta,
        image_prompt=new_prompt,
        rendered_image_url=final_url,
        base_image_url=base_url,
        user_message=decision.get("user_message", ""),
        ai_response=decision.get("ai_response_to_user", ""),
        change_scope="base_image",
    )
    return version_id


async def _regen_full(
    post_id: str,
    decision: dict,
    current_post: dict,
    brand_context: dict | None,
    language: str,
) -> str:
    """Full regeneration — same as base_image but with all-new everything."""
    # Full regen delegates to base_image with all fields from decision
    return await _regen_base_image(
        post_id, decision, current_post, brand_context, language,
    )
