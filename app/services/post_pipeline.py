"""Two-phase post generation pipeline.

Phase 1: Generate copy only (cheap — single LLM call).
Phase 2: Generate images only for approved posts (expensive — Flux + Nano Banana).

This keeps the existing full pipeline working via ``generate_full_pipeline``
while enabling cost-efficient two-phase generation for new workflows.
"""

import asyncio

from app.core.logging import get_logger
from app.services import content_generator, supabase_client, nano_banana
from app.services.flux_kontext import (
    generate_image_with_reference,
    download_image_as_base64,
)
from app.services.image_storage import upload_image_to_fal
from app.services.prompt_optimizer import optimize_image_prompt
from app.providers import vertex_imagen
from app.services.image_service import enrich_image_prompt

logger = get_logger(__name__)

_FORMAT_ASPECT_RATIO: dict[str, str] = {
    "instagram_feed": "1:1",
    "instagram_story": "9:16",
    "facebook_post": "16:9",
    "linkedin_post": "16:9",
}

IMAGE_SEMAPHORE_LIMIT = 3


class PostPipeline:
    """Orchestrates post generation in separate phases."""

    # ------------------------------------------------------------------
    # Phase 1 — copy only
    # ------------------------------------------------------------------

    async def generate_copy_batch(
        self,
        job_id: str,
        post_ids: list[str],
        payload,  # SmartBatchRenderRequest
        language: str = "es",
    ) -> None:
        """Generate copy for all posts (single LLM call). No images.

        Each post is persisted with status='success', image_status='pending',
        rendered_image_url=None.
        """
        try:
            # Enrich context from Supabase if brand/draft IDs available
            logo_analysis = payload.logo_analysis
            product_analysis = payload.product_analysis
            if payload.draft_id or not logo_analysis:
                brand_ctx, pa_enriched, _products = (
                    await content_generator.enrich_context_from_supabase(
                        brand_id=None,
                        draft_id=payload.draft_id,
                    )
                )
                if not logo_analysis and brand_ctx.get("vision_analysis"):
                    logo_analysis = brand_ctx["vision_analysis"]
                if not product_analysis and pa_enriched:
                    product_analysis = pa_enriched

            # Single LLM call for all copies
            post_contents = await content_generator.generate_post_content(
                brand_name=payload.brand.name,
                campaign_description=payload.campaign.description,
                tone=payload.campaign.tone,
                extras=payload.campaign.extras,
                platform=payload.posts_config[0].platform,
                format=payload.posts_config[0].format,
                num_posts=len(payload.posts_config),
                brand_colors={
                    "primary": payload.brand.primary_color,
                    "secondary": payload.brand.secondary_color,
                    "accent": payload.brand.accent_color,
                },
                logo_analysis=logo_analysis,
                product_analysis=product_analysis,
                language=language,
            )

            completed = 0
            for idx, _config in enumerate(payload.posts_config):
                post_id = post_ids[idx]
                try:
                    content = post_contents[idx]
                    await supabase_client.update_post_copy_success(
                        post_id=post_id,
                        headline=content["headline"],
                        body=content["body"],
                        cta=content["cta"],
                        image_prompt=content["image_prompt"],
                    )
                    # Create version 1 (copy only, no image)
                    await supabase_client.create_post_version(
                        post_id=post_id,
                        version_number=1,
                        headline=content["headline"],
                        body=content["body"],
                        cta=content["cta"],
                        image_prompt=content["image_prompt"],
                        rendered_image_url="",
                        base_image_url="",
                        change_scope="initial_copy",
                    )
                except Exception as exc:
                    logger.error("copy_post_failed", index=idx, post_id=post_id, error=str(exc))
                    await supabase_client.update_post_error(post_id, str(exc))

                completed += 1
                await supabase_client.update_job_progress(job_id, completed)

            await supabase_client.complete_job(job_id)

        except Exception as exc:
            logger.error("copy_batch_failed", job_id=job_id, error=str(exc))
            await supabase_client.fail_job(job_id, str(exc))

    # ------------------------------------------------------------------
    # Phase 2 — single image
    # ------------------------------------------------------------------

    async def generate_image_for_post(
        self,
        post_id: str,
        brand: dict,
        product_images: list[str] | None = None,
        include_logo_in_image: bool = False,
        include_text_in_image: bool = False,
        language: str = "es",
    ) -> None:
        """Generate image for ONE approved post.

        1. Load post from DB (must be status=success, image_status=pending)
        2. Mark image_status='generating'
        3. Flux Kontext if product_images, else Vertex fallback
        4. Nano Banana overlay if requested
        5. Upload to Supabase Storage
        6. Update post: image_status='ready', rendered_image_url=url
        """
        post = await supabase_client.get_post(post_id)
        if not post:
            raise ValueError(f"Post {post_id} not found")

        await supabase_client.update_post_fields(post_id, {"image_status": "generating"})

        try:
            job_id = post["job_id"]
            aspect_ratio = _FORMAT_ASPECT_RATIO.get(post.get("format", "instagram_feed"), "1:1")

            # Optimize image prompt ES→EN before sending to image models
            prompt_en = await optimize_image_prompt(
                prompt_es=post.get("image_prompt", ""),
                brand_context=brand,
                platform=post.get("platform"),
                format_label=post.get("format"),
            )
            # Persist the EN prompt for debugging / re-generation
            await supabase_client.update_post_fields(post_id, {"image_prompt_en": prompt_en})

            # Upload product images to fal.ai URLs
            product_image_urls: list[str] = []
            if product_images:
                for img_b64 in product_images:
                    url = await upload_image_to_fal(img_b64)
                    product_image_urls.append(url)

            use_flux = bool(product_image_urls)
            base_image_url_for_version = ""

            if use_flux:
                product_url = product_image_urls[0]

                # Flux Kontext Pro — product in scene
                flux_image_url = await generate_image_with_reference(
                    prompt=prompt_en,
                    reference_image_url=product_url,
                    aspect_ratio=aspect_ratio,
                )

                # Save base image (pre-overlays) to storage
                base_b64 = await download_image_as_base64(flux_image_url)
                base_filename = f"{job_id}/{post_id}_base.png"
                base_image_url_for_version = await supabase_client.upload_image_to_storage(
                    base_b64, base_filename,
                )

                # Nano Banana overlay if requested
                if include_logo_in_image or include_text_in_image:
                    logo_url = None
                    if include_logo_in_image and brand.get("logo_b64"):
                        logo_url = await upload_image_to_fal(brand["logo_b64"])

                    enhanced_url = await nano_banana.enhance_post_image(
                        base_image_url=flux_image_url,
                        logo_url=logo_url,
                        headline=post["headline"] if include_text_in_image else None,
                        cta=post["cta"] if include_text_in_image else None,
                        brand_colors={
                            "primary_color": brand.get("primary_color", "#000000"),
                            "secondary_color": brand.get("secondary_color", "#ffffff"),
                        },
                        include_logo=include_logo_in_image,
                        include_text=include_text_in_image,
                        language=language,
                    )
                    image_b64 = await download_image_as_base64(enhanced_url)
                else:
                    image_b64 = base_b64
            else:
                image_b64 = await vertex_imagen.generate_image(
                    enrich_image_prompt(prompt_en)
                )

            # Upload final image to Supabase Storage
            filename = f"{job_id}/{post_id}.png"
            image_url = await supabase_client.upload_image_to_storage(image_b64, filename)

            # Update post
            await supabase_client.update_post_fields(post_id, {
                "image_status": "ready",
                "rendered_image_url": image_url,
            })
            if base_image_url_for_version:
                await supabase_client.update_post_fields(post_id, {
                    "base_image_url": base_image_url_for_version,
                })

            logger.info("image_generated", post_id=post_id, image_url=image_url)

        except Exception as exc:
            logger.error("image_generation_failed", post_id=post_id, error=str(exc))
            await supabase_client.update_post_fields(post_id, {
                "image_status": "error",
                "error_message": str(exc),
            })
            raise

    # ------------------------------------------------------------------
    # Phase 2 — batch images (parallel with semaphore)
    # ------------------------------------------------------------------

    async def generate_images_batch(
        self,
        post_ids: list[str],
        brand: dict,
        product_images: list[str] | None = None,
        include_logo_in_image: bool = False,
        include_text_in_image: bool = False,
        language: str = "es",
    ) -> dict:
        """Generate images for multiple approved posts in parallel.

        Uses asyncio.Semaphore(3) to respect fal.ai rate limits.

        Returns: {"succeeded": [post_ids], "failed": [(post_id, error)]}
        """
        semaphore = asyncio.Semaphore(IMAGE_SEMAPHORE_LIMIT)

        async def bounded(post_id: str) -> tuple[str, str | None]:
            async with semaphore:
                try:
                    await self.generate_image_for_post(
                        post_id=post_id,
                        brand=brand,
                        product_images=product_images,
                        include_logo_in_image=include_logo_in_image,
                        include_text_in_image=include_text_in_image,
                        language=language,
                    )
                    return (post_id, None)
                except Exception as e:
                    logger.error("batch_image_failed", post_id=post_id, error=str(e))
                    return (post_id, str(e))

        results = await asyncio.gather(*[bounded(pid) for pid in post_ids])

        succeeded = [pid for pid, err in results if err is None]
        failed = [(pid, err) for pid, err in results if err is not None]

        logger.info(
            "batch_images_done",
            total=len(post_ids),
            succeeded=len(succeeded),
            failed=len(failed),
        )
        return {"succeeded": succeeded, "failed": failed}

    # ------------------------------------------------------------------
    # Full pipeline (backward compat)
    # ------------------------------------------------------------------

    async def generate_full_pipeline(
        self,
        job_id: str,
        post_ids: list[str],
        payload,  # SmartBatchRenderRequest
        language: str = "es",
    ) -> None:
        """Full pipeline: copy + images in one pass (backward compat).

        Internally: generate_copy_batch → auto-approve → generate_images_batch.
        """
        try:
            # Phase 1: generate copy
            await self.generate_copy_batch(
                job_id=job_id,
                post_ids=post_ids,
                payload=payload,
                language=language,
            )

            # Auto-approve all successful posts
            posts = await supabase_client.list_posts_by_job(job_id)
            successful_ids = []
            for post in posts:
                if post["status"] == "success":
                    await supabase_client.update_post_fields(post["id"], {
                        "approval_status": "approved",
                    })
                    successful_ids.append(post["id"])

            if not successful_ids:
                return

            # Re-open job for image phase
            client = supabase_client.get_client()
            client.table("generation_jobs").update({
                "status": "processing",
            }).eq("id", job_id).execute()

            # Build brand dict for image generation
            brand_dict = {
                "logo_b64": payload.brand.logo_b64,
                "primary_color": payload.brand.primary_color,
                "secondary_color": payload.brand.secondary_color,
                "accent_color": payload.brand.accent_color,
            }

            # Phase 2: generate images
            await self.generate_images_batch(
                post_ids=successful_ids,
                brand=brand_dict,
                product_images=payload.product_images,
                include_logo_in_image=payload.include_logo_in_image,
                include_text_in_image=payload.include_text_in_image,
                language=language,
            )

            await supabase_client.complete_job(job_id)

        except Exception as exc:
            logger.error("full_pipeline_failed", job_id=job_id, error=str(exc))
            await supabase_client.fail_job(job_id, str(exc))


# Module-level instance for easy import
post_pipeline = PostPipeline()
