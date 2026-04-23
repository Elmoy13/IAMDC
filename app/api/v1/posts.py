import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.core.exceptions import ImageGenerationError
from app.core.logging import get_logger
from app.middleware.auth import get_current_user, get_user_agency
from app.providers import vertex_imagen
from app.schemas.post import (
    ApproveAndGenerateImageResponse,
    BatchRenderRequest,
    BatchRenderResponse,
    BatchResultItem,
    Dimensions,
    EditChatHistoryResponse,
    EditChatRequest,
    EditChatResponse,
    GenerateAllApprovedImagesResponse,
    GenerateResponse,
    JobStatusResponse,
    PostVersionsResponse,
    PostVersionItem,
    RenderPostRequest,
    RenderPostResponse,
    RestoreVersionResponse,
    SmartBatchRenderRequest,
    SmartBatchRenderResponse,
    TemplateMeta,
    TemplatesListResponse,
    VideoGenerateRequest,
    VideoGenerateResponse,
    VideoStatusResponse,
)
from app.services import content_generator, template_generator, template_renderer
from app.services import supabase_client
from app.services.image_service import enrich_image_prompt
from app.services.flux_kontext import (
    generate_image_with_reference,
    download_image_as_base64,
)
from app.services.image_storage import upload_image_to_fal
from app.services import video_generator
from app.services import nano_banana
from app.services.language_detector import detect_language
from app.services import edit_director, post_regenerator
from app.services.post_pipeline import post_pipeline

logger = get_logger(__name__)

posts_router = APIRouter(prefix="/posts", tags=["posts"])
templates_router = APIRouter(prefix="/templates", tags=["templates"])

_FORMAT_DIMENSIONS: dict[str, Dimensions] = {
    "instagram_feed": Dimensions(width=1080, height=1080),
    "instagram_story": Dimensions(width=1080, height=1920),
    "facebook_post": Dimensions(width=1200, height=630),
    "linkedin_post": Dimensions(width=1200, height=627),
}

_FORMAT_ASPECT_RATIO: dict[str, str] = {
    "instagram_feed": "1:1",
    "instagram_story": "9:16",
    "facebook_post": "16:9",
    "linkedin_post": "16:9",
}

# ---------------------------------------------------------------------------
# Shared pipeline helper
# ---------------------------------------------------------------------------

async def _render_single(
    format: str,
    brand: dict,
    copy: dict,
    image_prompt: str,
    style_description: str,
) -> tuple[str, str]:
    """Run the full Vertex AI → Nova Pro → Playwright pipeline.

    Returns:
        (rendered_post_data_url, html_content)
    """
    background_b64 = await vertex_imagen.generate_image(
        enrich_image_prompt(image_prompt)
    )

    html_content = await template_generator.generate_post_template(
        format=format,
        brand=brand,
        copy=copy,
        style_description=style_description,
        background_image_b64=background_b64,
    )

    dims = _FORMAT_DIMENSIONS[format]
    rendered = await template_renderer.render_html_to_png(
        html_content=html_content,
        width=dims.width,
        height=dims.height,
    )
    return rendered, html_content


# ---------------------------------------------------------------------------
# POST /api/v1/posts/render
# ---------------------------------------------------------------------------

@posts_router.post("/render", response_model=RenderPostResponse, deprecated=True)
async def render_post(
    payload: RenderPostRequest,
    _user: dict = Depends(get_current_user),
) -> RenderPostResponse:
    """DEPRECATED — Use POST /posts/generate instead.

    Generate a background with Vertex AI, build a post template with Claude,
    and render it to PNG with Playwright."""
    logger.warning("deprecated_endpoint_called", endpoint="/posts/render")

    if payload.format not in _FORMAT_DIMENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported format: {payload.format!r}. "
                f"Valid values: {list(_FORMAT_DIMENSIONS)}"
            ),
        )

    try:
        rendered, html_content = await asyncio.wait_for(
            _render_single(
                format=payload.format,
                brand=payload.brand.model_dump(),
                copy=payload.post_copy.model_dump(),
                image_prompt=payload.image_prompt,
                style_description=payload.style_description,
            ),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Render pipeline timed out (90 s)",
        )
    except ImageGenerationError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    dims = _FORMAT_DIMENSIONS[payload.format]
    return RenderPostResponse(
        rendered_post=rendered,
        format=payload.format,
        dimensions=dims,
        html_preview=html_content,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/posts/render-batch-legacy  (legacy — caller supplies copy + image prompts)
# ---------------------------------------------------------------------------

@posts_router.post("/render-batch-legacy", response_model=BatchRenderResponse, deprecated=True)
async def render_batch(
    payload: BatchRenderRequest,
    _user: dict = Depends(get_current_user),
) -> BatchRenderResponse:
    """DEPRECATED — Use POST /posts/generate instead.

    Render multiple posts for a content grid sequentially.
    Each post is processed one at a time to avoid overloading Vertex AI.
    Failures are captured per-item and do not abort the whole batch.
    """
    logger.warning("deprecated_endpoint_called", endpoint="/posts/render-batch-legacy")
    results: list[BatchResultItem] = []
    brand = payload.brand.model_dump()

    for idx, post in enumerate(payload.posts):
        if post.format not in _FORMAT_DIMENSIONS:
            results.append(
                BatchResultItem(
                    index=idx,
                    rendered_post=None,
                    format=post.format,
                    status="error",
                    error=f"Unsupported format: {post.format!r}",
                )
            )
            continue

        try:
            rendered, _ = await asyncio.wait_for(
                _render_single(
                    format=post.format,
                    brand=brand,
                    copy=post.post_copy.model_dump(),
                    image_prompt=post.image_prompt,
                    style_description=post.style_description,
                ),
                timeout=90.0,
            )
            results.append(
                BatchResultItem(
                    index=idx,
                    rendered_post=rendered,
                    format=post.format,
                    status="success",
                )
            )
        except asyncio.TimeoutError:
            results.append(
                BatchResultItem(
                    index=idx,
                    rendered_post=None,
                    format=post.format,
                    status="error",
                    error="Timed out (90 s)",
                )
            )
        except Exception as exc:
            logger.error("batch_item_failed", index=idx, error=str(exc))
            results.append(
                BatchResultItem(
                    index=idx,
                    rendered_post=None,
                    format=post.format,
                    status="error",
                    error=str(exc),
                )
            )

    return BatchRenderResponse(results=results)


# ---------------------------------------------------------------------------
# POST /api/v1/posts/render-batch  (intelligent — LLM generates copy + prompts)
# ---------------------------------------------------------------------------

@posts_router.post("/render-batch", response_model=SmartBatchRenderResponse, deprecated=True)
async def smart_render_batch(
    payload: SmartBatchRenderRequest,
    _user: dict = Depends(get_current_user),
) -> SmartBatchRenderResponse:
    """DEPRECATED — Use POST /posts/generate instead.

    Full intelligent pipeline:
    1. One LLM call generates copy + image prompts for ALL posts from the brief.
    2. For each post: Vertex AI → background PNG → Nova Pro → HTML → Playwright → PNG.
    """
    logger.warning("deprecated_endpoint_called", endpoint="/posts/render-batch")
    num_posts = len(payload.posts_config)

    # STEP 1 — Generate all content with a single LLM call
    try:
        post_contents = await asyncio.wait_for(
            content_generator.generate_post_content(
                brand_name=payload.brand.name,
                campaign_description=payload.campaign.description,
                tone=payload.campaign.tone,
                extras=payload.campaign.extras,
                platform=payload.posts_config[0].platform,
                format=payload.posts_config[0].format,
                num_posts=num_posts,
                brand_colors={
                    "primary": payload.brand.primary_color,
                    "secondary": payload.brand.secondary_color,
                    "accent": payload.brand.accent_color,
                },
                logo_analysis=payload.logo_analysis,
                product_analysis=payload.product_analysis,
                language=payload.language if payload.language != "auto" else "es",
            ),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Content generation timed out (60 s)",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Content generation failed: {exc}",
        )

    # Build brand dict: merge BrandInputFull → same shape as BrandInput expects
    brand_dict = {
        "logo_b64": payload.brand.logo_b64,
        "primary_color": payload.brand.primary_color,
        "secondary_color": payload.brand.secondary_color,
        "accent_color": payload.brand.accent_color,
        "contrast_color": payload.brand.contrast_color,
        "font_family": payload.brand.font_family,
    }

    # STEP 1.5 — Upload product images to public URLs (if provided)
    product_image_urls: list[str] = []
    use_flux = bool(payload.product_images)

    if use_flux:
        for img_b64 in payload.product_images:
            try:
                url = await upload_image_to_fal(img_b64)
                product_image_urls.append(url)
            except Exception as exc:
                logger.error("product_image_upload_failed", error=str(exc))

        if not product_image_urls:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to upload product images. At least one is required for Flux.",
            )

    # STEP 2 — Render each post sequentially
    results: list[BatchResultItem] = []

    for idx, config in enumerate(payload.posts_config):
        if config.format not in _FORMAT_DIMENSIONS:
            results.append(BatchResultItem(
                index=idx, rendered_post=None, format=config.format,
                status="error", error=f"Unsupported format: {config.format!r}",
            ))
            continue

        content = post_contents[idx]

        try:
            if use_flux:
                # --- Flux path (image-to-image) ---
                product_url = product_image_urls[idx % len(product_image_urls)]
                aspect_ratio = _FORMAT_ASPECT_RATIO.get(config.format, "1:1")

                # Step 1: Flux Kontext Pro — product in scene (clean)
                flux_image_url = await generate_image_with_reference(
                    prompt=content["image_prompt"],
                    reference_image_url=product_url,
                    aspect_ratio=aspect_ratio,
                )

                # Step 2: Nano Banana 2 Edit — add logo and/or text if requested
                if payload.include_logo_in_image or payload.include_text_in_image:
                    logo_url = None
                    if payload.include_logo_in_image and (payload.brand.logo_b64 or ""):
                        logo_url = await upload_image_to_fal(payload.brand.logo_b64)

                    enhanced_url = await nano_banana.enhance_post_image(
                        base_image_url=flux_image_url,
                        logo_url=logo_url,
                        headline=content["headline"] if payload.include_text_in_image else None,
                        cta=content["cta"] if payload.include_text_in_image else None,
                        brand_colors={
                            "primary_color": payload.brand.primary_color,
                            "secondary_color": payload.brand.secondary_color,
                        },
                        include_logo=payload.include_logo_in_image,
                        include_text=payload.include_text_in_image,
                        language=payload.language if payload.language != "auto" else "es",
                    )
                    background_b64 = await download_image_as_base64(enhanced_url)
                else:
                    background_b64 = await download_image_as_base64(flux_image_url)
            else:
                # --- Vertex AI fallback (text-to-image, no product photos) ---
                background_b64 = await vertex_imagen.generate_image(
                    enrich_image_prompt(content["image_prompt"])
                )

            # Skip HTML logo if it's already in the AI-generated image
            template_brand = dict(brand_dict)
            if payload.include_logo_in_image:
                template_brand["logo_b64"] = ""

            html_content = await template_generator.generate_post_template(
                format=config.format,
                brand=template_brand,
                copy={
                    "headline": content["headline"],
                    "body": content["body"],
                    "cta": content["cta"],
                },
                style_description=content["style_description"],
                background_image_b64=background_b64,
            )

            dims = _FORMAT_DIMENSIONS[config.format]
            rendered = await template_renderer.render_html_to_png(
                html_content=html_content,
                width=dims.width,
                height=dims.height,
            )

            results.append(BatchResultItem(
                index=idx,
                rendered_post=rendered,
                format=config.format,
                status="success",
                headline=content["headline"],
                body=content["body"],
                cta=content["cta"],
                image_prompt=content["image_prompt"],
            ))
        except asyncio.TimeoutError:
            results.append(BatchResultItem(
                index=idx, rendered_post=None, format=config.format,
                status="error", error="Render timed out (120 s)",
            ))
        except Exception as exc:
            logger.error("smart_batch_item_failed", index=idx, error=str(exc))
            results.append(BatchResultItem(
                index=idx, rendered_post=None, format=config.format,
                status="error", error=str(exc),
            ))

    return SmartBatchRenderResponse(results=results)


# ---------------------------------------------------------------------------
# POST /api/v1/posts/generate  (async job-based — returns immediately)
# ---------------------------------------------------------------------------

@posts_router.post("/generate", response_model=GenerateResponse)
async def start_generation(
    payload: SmartBatchRenderRequest,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_user_agency),
) -> GenerateResponse:
    """Start async post generation. Returns a job_id immediately.

    The actual generation runs in the background; each finished post is
    saved to Supabase as it completes. The frontend polls GET /job/{job_id}.
    """
    total_posts = len(payload.posts_config)

    # Resolve language
    lang = payload.language
    if lang == "auto":
        chat_msgs = payload.chat_messages or []
        lang = await detect_language(
            brand_name=payload.brand.name,
            campaign_brief=payload.campaign.description,
            chat_messages=chat_msgs,
        )

    # Handle draft linkage
    draft_id = payload.draft_id
    if draft_id:
        try:
            client = supabase_client.get_client()
            draft_result = (
                client.table("parrilla_drafts")
                .select("config")
                .eq("id", draft_id)
                .eq("agency_id", agency["agency_id"])
                .single()
                .execute()
            )
            if draft_result.data:
                client.table("parrilla_drafts").update({
                    "status": "generating",
                }).eq("id", draft_id).execute()
        except Exception as exc:
            logger.error("draft_link_failed", draft_id=draft_id, error=str(exc))
            raise HTTPException(
                status_code=500,
                detail=f"Failed to link draft {draft_id}. Please retry or create a new draft.",
            )

    # Always persist the full payload as job config so the approve endpoint
    # has brand/product context even if the draft is stale or missing.
    job_config = {
        "brand": payload.brand.model_dump(),
        "campaign": payload.campaign.model_dump(),
        "product_images": payload.product_images or [],
        "include_logo_in_image": payload.include_logo_in_image,
        "include_text_in_image": payload.include_text_in_image,
        "language": payload.language,
    }

    # Create job in Supabase
    job_id = await supabase_client.create_job(
        total_posts=total_posts,
        brand_name=payload.brand.name,
        campaign_description=payload.campaign.description,
        language=lang,
        agency_id=agency["agency_id"],
        draft_id=draft_id,
        config=job_config,
    )

    # Create placeholder rows for each post
    post_ids: list[str] = []
    for i, config in enumerate(payload.posts_config):
        post_id = await supabase_client.create_post_placeholder(
            job_id=job_id,
            index=i,
            platform=config.platform,
            format=config.format,
        )
        post_ids.append(post_id)

    # Launch background generation
    background_tasks.add_task(
        post_pipeline.generate_full_pipeline,
        job_id=job_id,
        post_ids=post_ids,
        payload=payload,
        language=lang,
    )

    return GenerateResponse(
        job_id=job_id,
        total_posts=total_posts,
        status="processing",
    )


# ---------------------------------------------------------------------------
# POST /api/v1/posts/generate-copy-only  (Phase 1 — copy, no images)
# ---------------------------------------------------------------------------

@posts_router.post("/generate-copy-only", response_model=GenerateResponse, deprecated=True)
async def generate_copy_only(
    payload: SmartBatchRenderRequest,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_user_agency),
) -> GenerateResponse:
    """DEPRECATED — Use POST /posts/generate instead (full pipeline).

    Generate job + copies of posts. Images are NOT generated.
    The user must call /posts/{id}/approve-and-generate-image for each approved
    post, or /posts/job/{id}/generate-all-approved-images for bulk.
    """
    logger.warning("deprecated_endpoint_called", endpoint="/posts/generate-copy-only")
    total_posts = len(payload.posts_config)

    # Resolve language
    lang = payload.language
    if lang == "auto":
        chat_msgs = payload.chat_messages or []
        lang = await detect_language(
            brand_name=payload.brand.name,
            campaign_brief=payload.campaign.description,
            chat_messages=chat_msgs,
        )

    # Handle draft linkage
    draft_id = payload.draft_id
    if draft_id:
        try:
            client = supabase_client.get_client()
            draft_result = (
                client.table("parrilla_drafts")
                .select("config")
                .eq("id", draft_id)
                .eq("agency_id", agency["agency_id"])
                .single()
                .execute()
            )
            if draft_result.data:
                client.table("parrilla_drafts").update({
                    "status": "generating",
                }).eq("id", draft_id).execute()
        except Exception as exc:
            logger.error("draft_link_failed", draft_id=draft_id, error=str(exc))
            raise HTTPException(
                status_code=500,
                detail=f"Failed to link draft {draft_id}. Please retry or create a new draft.",
            )

    # Always persist the full payload as job config so the approve endpoint
    # has brand/product context even if the draft is stale or missing.
    job_config = {
        "brand": payload.brand.model_dump(),
        "campaign": payload.campaign.model_dump(),
        "product_images": payload.product_images or [],
        "include_logo_in_image": payload.include_logo_in_image,
        "include_text_in_image": payload.include_text_in_image,
        "language": payload.language,
    }

    # Create job in Supabase
    job_id = await supabase_client.create_job(
        total_posts=total_posts,
        brand_name=payload.brand.name,
        campaign_description=payload.campaign.description,
        language=lang,
        agency_id=agency["agency_id"],
        draft_id=draft_id,
        config=job_config,
    )

    # Create placeholder rows
    post_ids: list[str] = []
    for i, config in enumerate(payload.posts_config):
        post_id = await supabase_client.create_post_placeholder(
            job_id=job_id,
            index=i,
            platform=config.platform,
            format=config.format,
        )
        post_ids.append(post_id)

    # Background: generate copy only
    background_tasks.add_task(
        post_pipeline.generate_copy_batch,
        job_id=job_id,
        post_ids=post_ids,
        payload=payload,
        language=lang,
    )

    return GenerateResponse(
        job_id=job_id,
        total_posts=total_posts,
        status="processing",
    )


# ---------------------------------------------------------------------------
# POST /api/v1/posts/{post_id}/approve-and-generate-image
# ---------------------------------------------------------------------------

@posts_router.post(
    "/{post_id}/approve-and-generate-image",
    response_model=ApproveAndGenerateImageResponse,
)
async def approve_and_generate_image(
    post_id: str,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_user_agency),
) -> ApproveAndGenerateImageResponse:
    """Approve a single post and trigger image generation in background."""
    post = await supabase_client.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post["status"] != "success":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Copy not ready yet",
        )
    if post.get("image_status") and post["image_status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image already {post['image_status']}",
        )

    # Approve in DB
    await supabase_client.update_post_fields(post_id, {
        "approval_status": "approved",
        "approved_at": datetime.now(timezone.utc).isoformat(),
    })

    # Fetch job config for brand/product images
    job = await supabase_client.get_job(post["job_id"])
    job_config = job.get("config") or {} if job else {}

    background_tasks.add_task(
        post_pipeline.generate_image_for_post,
        post_id=post_id,
        brand=job_config.get("brand", {}),
        product_images=job_config.get("product_images"),
        include_logo_in_image=job_config.get("include_logo_in_image", False),
        include_text_in_image=job_config.get("include_text_in_image", False),
        language=job.get("language", "es") if job else "es",
    )

    return ApproveAndGenerateImageResponse(
        post_id=post_id,
        approval_status="approved",
        image_status="generating",
    )


# ---------------------------------------------------------------------------
# POST /api/v1/posts/job/{job_id}/generate-all-approved-images
# ---------------------------------------------------------------------------

@posts_router.post(
    "/job/{job_id}/generate-all-approved-images",
    response_model=GenerateAllApprovedImagesResponse,
)
async def generate_all_approved_images(
    job_id: str,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_user_agency),
) -> GenerateAllApprovedImagesResponse:
    """Generate images for ALL approved posts in a job (parallel with Semaphore(3))."""
    posts = await supabase_client.list_posts_by_job(job_id)
    approved_pending = [
        p for p in posts
        if p.get("approval_status") == "approved"
        and p.get("image_status", "pending") == "pending"
    ]

    if not approved_pending:
        return GenerateAllApprovedImagesResponse(
            count=0,
            status="no_pending",
            message="No approved posts pending images",
        )

    post_ids = [p["id"] for p in approved_pending]

    job = await supabase_client.get_job(job_id)
    job_config = job.get("config") or {} if job else {}

    background_tasks.add_task(
        post_pipeline.generate_images_batch,
        post_ids=post_ids,
        brand=job_config.get("brand", {}),
        product_images=job_config.get("product_images"),
        include_logo_in_image=job_config.get("include_logo_in_image", False),
        include_text_in_image=job_config.get("include_text_in_image", False),
        language=job.get("language", "es") if job else "es",
    )

    return GenerateAllApprovedImagesResponse(
        count=len(post_ids),
        status="generating_images",
    )


# ---------------------------------------------------------------------------
# GET /api/v1/posts/job/{job_id}
# ---------------------------------------------------------------------------

@posts_router.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    agency: dict = Depends(get_user_agency),
) -> JobStatusResponse:
    """Return the current state of a generation job and all its posts."""
    try:
        result = await supabase_client.get_job_status(job_id, agency_id=agency["agency_id"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {exc}",
        )
    return JobStatusResponse(**result)


# ---------------------------------------------------------------------------
# POST /api/v1/posts/{post_id}/video  (start video generation)
# ---------------------------------------------------------------------------

@posts_router.post("/{post_id}/video", response_model=VideoGenerateResponse)
async def start_video_generation(
    post_id: str,
    background_tasks: BackgroundTasks,
    payload: VideoGenerateRequest | None = None,
    agency: dict = Depends(get_user_agency),
) -> VideoGenerateResponse:
    """Start video generation for an existing post.

    Fetches the post's rendered image, generates a motion prompt with Nova Pro,
    then submits to Kling via fal.ai. Runs in background; poll status with GET.
    """
    post = await supabase_client.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if not post.get("rendered_image_url"):
        raise HTTPException(
            status_code=400,
            detail="Post has no rendered image yet. Generate the image first.",
        )

    # Mark as processing
    await supabase_client.update_post_video_status(post_id, "processing")

    duration = payload.duration if payload else "5"
    aspect_ratio = payload.aspect_ratio if payload else ""

    background_tasks.add_task(
        _generate_video_background,
        post=post,
        duration=duration,
        aspect_ratio_override=aspect_ratio,
    )

    return VideoGenerateResponse(post_id=post_id, video_status="processing")


# ---------------------------------------------------------------------------
# GET /api/v1/posts/{post_id}/video  (poll status)
# ---------------------------------------------------------------------------

@posts_router.get("/{post_id}/video/status", response_model=VideoStatusResponse)
@posts_router.get("/{post_id}/video", response_model=VideoStatusResponse)
async def get_video_status(
    post_id: str,
    agency: dict = Depends(get_user_agency),
) -> VideoStatusResponse:
    """Return the current video generation status for a post."""
    post = await supabase_client.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    return VideoStatusResponse(
        post_id=post_id,
        video_status=post.get("video_status", "none"),
        video_url=post.get("video_url"),
        video_error=post.get("video_error"),
        motion_prompt=post.get("motion_prompt"),
    )


# ---------------------------------------------------------------------------
# Video background worker
# ---------------------------------------------------------------------------

async def _generate_video_background(
    post: dict,
    duration: str,
    aspect_ratio_override: str,
) -> None:
    """Generate a video from a post's rendered image in background."""
    post_id = post["id"]
    try:
        image_url = post["rendered_image_url"]
        fmt = post.get("format", "instagram_feed")
        aspect_ratio = aspect_ratio_override or _FORMAT_ASPECT_RATIO.get(fmt, "9:16")

        # Nova Pro VISION analyzes the actual image and generates a motion prompt
        motion_prompt = await video_generator.generate_motion_prompt(image_url)

        # Generate video (submit + poll until done)
        video_url = await video_generator.generate_video(
            image_url=image_url,
            prompt=motion_prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
        )

        # Download and re-upload to Supabase Storage
        video_bytes = await video_generator.download_video_bytes(video_url)
        filename = f"videos/{post_id}.mp4"
        supabase_url = await supabase_client.upload_video_to_storage(
            video_bytes, filename,
        )

        await supabase_client.update_post_video(
            post_id=post_id,
            video_url=supabase_url,
            motion_prompt=motion_prompt,
        )
        logger.info("video_generation_success", post_id=post_id)

    except Exception as exc:
        logger.error("video_generation_failed", post_id=post_id, error=str(exc))
        await supabase_client.update_post_video_status(post_id, "error", str(exc))


# ---------------------------------------------------------------------------
# POST /api/v1/posts/{post_id}/edit-chat  (iterative editing)
# ---------------------------------------------------------------------------

@posts_router.post("/{post_id}/edit-chat", response_model=EditChatResponse)
async def edit_chat(
    post_id: str,
    payload: EditChatRequest,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_user_agency),
) -> EditChatResponse:
    """Chat-based iterative editing for a post.

    Analyzes the user's feedback, decides what to change, and regenerates
    only what's needed in the background.
    """
    post = await supabase_client.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.get("edit_status") == "regenerating":
        raise HTTPException(
            status_code=409,
            detail="Post is already being edited. Wait for the current edit to finish.",
        )

    # Resolve user message from quick_action or direct input
    user_message = payload.user_message
    if payload.quick_action and payload.quick_action in edit_director.QUICK_ACTIONS:
        user_message = edit_director.QUICK_ACTIONS[payload.quick_action]

    if not user_message:
        raise HTTPException(status_code=400, detail="Provide user_message or quick_action")

    # Fetch context
    job_data = await supabase_client.get_job_status(post["job_id"])
    job = job_data["job"]
    chat_history = await supabase_client.get_edit_chat_history(post_id)
    language = job.get("language", "es")

    # Analyze the edit request with Nova Pro Vision
    decision = await edit_director.analyze_edit_request(
        post=post,
        brand_context={"brand_name": job.get("brand_name", "")},
        campaign_brief=job.get("campaign_description", ""),
        user_message=user_message,
        chat_history=chat_history,
        current_image_url=post.get("rendered_image_url", ""),
        language=language,
    )

    # Inject the original user_message into decision for version tracking
    decision["user_message"] = user_message

    # Save chat messages
    await supabase_client.add_edit_chat_message(post_id, "user", user_message)
    ai_response = decision.get("ai_response_to_user", "Regenerando...")
    await supabase_client.add_edit_chat_message(post_id, "assistant", ai_response)

    # Create a placeholder version_id
    version_number = 1
    versions = await supabase_client.get_post_versions(post_id)
    if versions:
        version_number = max(v["version_number"] for v in versions) + 1

    # For copy_only, do it synchronously (instant)
    if decision["change_scope"] == "copy_only":
        version_id = await post_regenerator.regenerate_post(
            post_id=post_id,
            edit_decision=decision,
            current_post=post,
            language=language,
        )
        return EditChatResponse(
            ai_response=ai_response,
            change_scope=decision["change_scope"],
            version_id=version_id,
            status="completed",
        )

    # For everything else, run in background
    await supabase_client.update_post_edit_status(post_id, "regenerating")

    background_tasks.add_task(
        post_regenerator.regenerate_post,
        post_id=post_id,
        edit_decision=decision,
        current_post=post,
        language=language,
    )

    return EditChatResponse(
        ai_response=ai_response,
        change_scope=decision["change_scope"],
        version_id="pending",
        status="regenerating",
    )


# ---------------------------------------------------------------------------
# GET /api/v1/posts/{post_id}/edit-chat  (chat history)
# ---------------------------------------------------------------------------

@posts_router.get("/{post_id}/edit-chat", response_model=EditChatHistoryResponse)
async def get_edit_chat(
    post_id: str,
    agency: dict = Depends(get_user_agency),
) -> EditChatHistoryResponse:
    """Return the full edit chat history for a post."""
    post = await supabase_client.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    messages = await supabase_client.get_edit_chat_history(post_id)
    return EditChatHistoryResponse(messages=messages)


# ---------------------------------------------------------------------------
# GET /api/v1/posts/{post_id}/versions
# ---------------------------------------------------------------------------

@posts_router.get("/{post_id}/versions", response_model=PostVersionsResponse)
async def get_post_versions(
    post_id: str,
    agency: dict = Depends(get_user_agency),
) -> PostVersionsResponse:
    """Return all versions of a post, newest first."""
    post = await supabase_client.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    raw_versions = await supabase_client.get_post_versions(post_id)
    versions = [
        PostVersionItem(
            id=v["id"],
            version_number=v["version_number"],
            rendered_image_url=v.get("rendered_image_url"),
            is_current=v.get("is_current", False),
            user_message=v.get("user_message"),
            change_scope=v.get("change_scope"),
            created_at=v.get("created_at", ""),
        )
        for v in raw_versions
    ]
    return PostVersionsResponse(versions=versions)


# ---------------------------------------------------------------------------
# POST /api/v1/posts/{post_id}/versions/{version_id}/restore
# ---------------------------------------------------------------------------

@posts_router.post(
    "/{post_id}/versions/{version_id}/restore",
    response_model=RestoreVersionResponse,
)
async def restore_version(
    post_id: str,
    version_id: str,
    agency: dict = Depends(get_user_agency),
) -> RestoreVersionResponse:
    """Restore a specific version of a post."""
    post = await supabase_client.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    version = await supabase_client.get_post_version(version_id)
    if not version or version.get("post_id") != post_id:
        raise HTTPException(status_code=404, detail="Version not found for this post")

    restored = await supabase_client.restore_post_version(post_id, version_id)

    return RestoreVersionResponse(
        post_id=post_id,
        restored_version=restored["version_number"],
    )


# ---------------------------------------------------------------------------
# GET /api/v1/templates
# ---------------------------------------------------------------------------

@templates_router.get("", response_model=TemplatesListResponse)
async def list_templates() -> TemplatesListResponse:
    """Return available static post templates with their metadata."""
    templates = [TemplateMeta(**t) for t in template_renderer.TEMPLATES_METADATA]
    return TemplatesListResponse(templates=templates)

