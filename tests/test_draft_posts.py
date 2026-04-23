"""Tests for the GET /drafts/{draft_id}/posts endpoint and related fixes."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.post_pipeline import PostPipeline
from app.schemas.post import (
    BrandInputFull,
    CampaignInput,
    PostConfigItem,
    SmartBatchRenderRequest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_AGENCY_ID = "00000000-0000-4000-a000-000000000001"


def _make_payload(
    num_posts: int = 3,
    draft_id: str | None = None,
    brand_id: str | None = None,
) -> SmartBatchRenderRequest:
    return SmartBatchRenderRequest(
        brand=BrandInputFull(
            name="TestBrand",
            logo_b64="data:image/png;base64,abc",
            primary_color="#FF0000",
            secondary_color="#00FF00",
            accent_color="#0000FF",
        ),
        campaign=CampaignInput(
            description="Summer sale campaign",
            tone="fun and casual",
        ),
        posts_config=[
            PostConfigItem(platform="instagram", format="instagram_feed")
            for _ in range(num_posts)
        ],
        language="es",
        draft_id=draft_id,
    )


def _mock_draft(draft_id: str = "draft-1", agency_id: str = FAKE_AGENCY_ID, brand_id: str | None = "brand-1"):
    return {
        "id": draft_id,
        "agency_id": agency_id,
        "brand_id": brand_id,
        "title": "Test Parrilla",
        "status": "generated",
        "config": {},
        "chat_messages": [],
        "selected_product_ids": [],
    }


def _mock_job(job_id: str = "job-1", draft_id: str = "draft-1"):
    return {
        "id": job_id,
        "draft_id": draft_id,
        "status": "completed",
        "total_posts": 3,
        "completed_posts": 3,
        "language": "es",
        "created_at": "2026-04-23T00:00:00Z",
    }


def _mock_post(post_id: str, job_id: str = "job-1"):
    return {
        "id": post_id,
        "job_id": job_id,
        "status": "success",
        "headline": f"Headline {post_id}",
        "body": f"Body {post_id}",
        "cta": "Buy Now",
        "image_prompt": "A scene",
        "image_status": "pending",
        "index": 0,
        "created_at": "2026-04-23T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# 1. GET /drafts/{draft_id}/posts — returns posts for a valid draft
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_draft_posts_returns_posts(client, monkeypatch):
    """Draft with jobs and posts should return full data."""
    draft = _mock_draft("draft-1")
    jobs = [_mock_job("job-1", "draft-1")]
    posts = [_mock_post("p1"), _mock_post("p2"), _mock_post("p3")]

    monkeypatch.setattr(
        "app.api.v1.drafts.supabase_client.get_draft",
        AsyncMock(return_value=draft),
    )
    monkeypatch.setattr(
        "app.api.v1.drafts.supabase_client.list_jobs_by_draft",
        AsyncMock(return_value=jobs),
    )
    monkeypatch.setattr(
        "app.api.v1.drafts.supabase_client.list_posts_by_job_ids",
        AsyncMock(return_value=posts),
    )

    resp = await client.get("/api/v1/drafts/draft-1/posts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["draft"]["id"] == "draft-1"
    assert data["draft"]["brand_id"] == "brand-1"
    assert len(data["jobs"]) == 1
    assert len(data["posts"]) == 3
    assert data["posts"][0]["headline"] == "Headline p1"


# ---------------------------------------------------------------------------
# 2. GET /drafts/{draft_id}/posts — multiple jobs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_draft_posts_multiple_jobs(client, monkeypatch):
    """Draft with multiple regeneration jobs should return posts from all."""
    draft = _mock_draft("draft-1")
    jobs = [_mock_job("job-1", "draft-1"), _mock_job("job-2", "draft-1")]
    posts = [_mock_post("p1", "job-1"), _mock_post("p2", "job-2")]

    monkeypatch.setattr(
        "app.api.v1.drafts.supabase_client.get_draft",
        AsyncMock(return_value=draft),
    )

    captured_job_ids = []

    async def mock_list_jobs(draft_id):
        return jobs

    async def mock_list_posts(job_ids):
        captured_job_ids.extend(job_ids)
        return posts

    monkeypatch.setattr("app.api.v1.drafts.supabase_client.list_jobs_by_draft", mock_list_jobs)
    monkeypatch.setattr("app.api.v1.drafts.supabase_client.list_posts_by_job_ids", mock_list_posts)

    resp = await client.get("/api/v1/drafts/draft-1/posts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["jobs"]) == 2
    assert len(data["posts"]) == 2
    assert set(captured_job_ids) == {"job-1", "job-2"}


# ---------------------------------------------------------------------------
# 3. GET /drafts/{draft_id}/posts — empty (no jobs yet)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_draft_posts_empty(client, monkeypatch):
    """Draft with no jobs should return empty lists."""
    draft = _mock_draft("draft-1")

    monkeypatch.setattr(
        "app.api.v1.drafts.supabase_client.get_draft",
        AsyncMock(return_value=draft),
    )
    monkeypatch.setattr(
        "app.api.v1.drafts.supabase_client.list_jobs_by_draft",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.api.v1.drafts.supabase_client.list_posts_by_job_ids",
        AsyncMock(return_value=[]),
    )

    resp = await client.get("/api/v1/drafts/draft-1/posts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["posts"] == []
    assert data["jobs"] == []


# ---------------------------------------------------------------------------
# 4. GET /drafts/{draft_id}/posts — wrong agency → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_draft_posts_wrong_agency(client, monkeypatch):
    """Draft belonging to a different agency should return 404."""
    draft = _mock_draft("draft-1", agency_id="other-agency-id")

    monkeypatch.setattr(
        "app.api.v1.drafts.supabase_client.get_draft",
        AsyncMock(return_value=draft),
    )

    resp = await client.get("/api/v1/drafts/draft-1/posts")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. GET /drafts/{draft_id}/posts — draft not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_draft_posts_not_found(client, monkeypatch):
    """Non-existent draft should return 404."""
    monkeypatch.setattr(
        "app.api.v1.drafts.supabase_client.get_draft",
        AsyncMock(return_value=None),
    )

    resp = await client.get("/api/v1/drafts/nonexistent/posts")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. generate_copy_batch fails job if all posts error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_copy_batch_fails_if_all_posts_error(monkeypatch):
    """If every individual post fails to persist, the job should be marked
    as failed (not completed)."""
    pipeline = PostPipeline()
    payload = _make_payload(num_posts=2)
    post_ids = ["p1", "p2"]

    # Mock content_generator to return content that will be used
    fake_contents = [
        {"headline": "H0", "body": "B0", "cta": "C0", "image_prompt": "IP0"},
        {"headline": "H1", "body": "B1", "cta": "C1", "image_prompt": "IP1"},
    ]

    async def mock_generate_content(**kwargs):
        return fake_contents

    async def mock_enrich(**kwargs):
        return {}, None, []

    monkeypatch.setattr(
        "app.services.post_pipeline.content_generator.generate_post_content",
        mock_generate_content,
    )
    monkeypatch.setattr(
        "app.services.post_pipeline.content_generator.enrich_context_from_supabase",
        mock_enrich,
    )

    # Make update_post_copy_success always raise
    async def mock_copy_fail(post_id, headline, body, cta, image_prompt):
        raise RuntimeError("Supabase column missing")

    monkeypatch.setattr(
        "app.services.post_pipeline.supabase_client.update_post_copy_success",
        mock_copy_fail,
    )
    monkeypatch.setattr(
        "app.services.post_pipeline.supabase_client.update_post_error",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.post_pipeline.supabase_client.update_job_progress",
        AsyncMock(),
    )

    fail_job_mock = AsyncMock()
    complete_job_mock = AsyncMock()
    monkeypatch.setattr("app.services.post_pipeline.supabase_client.fail_job", fail_job_mock)
    monkeypatch.setattr("app.services.post_pipeline.supabase_client.complete_job", complete_job_mock)

    await pipeline.generate_copy_batch(
        job_id="job-1",
        post_ids=post_ids,
        payload=payload,
        language="es",
    )

    # Job should be failed, NOT completed
    fail_job_mock.assert_called_once()
    assert "All posts failed" in fail_job_mock.call_args[0][1]
    complete_job_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 7. brand_id is propagated from draft to enrich
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brand_id_propagated_from_draft(monkeypatch):
    """When the payload has a draft_id, the pipeline should read brand_id
    from the draft and pass it to enrich_context_from_supabase."""
    pipeline = PostPipeline()
    payload = _make_payload(num_posts=1, draft_id="draft-123")
    post_ids = ["p1"]

    # Track what brand_id enrich receives
    enrich_calls = []

    async def mock_enrich(brand_id=None, draft_id=None):
        enrich_calls.append({"brand_id": brand_id, "draft_id": draft_id})
        return {}, None, []

    async def mock_get_draft(draft_id):
        return {"id": draft_id, "brand_id": "my-brand-42"}

    fake_contents = [
        {"headline": "H0", "body": "B0", "cta": "C0", "image_prompt": "IP0"},
    ]

    monkeypatch.setattr(
        "app.services.post_pipeline.supabase_client.get_draft",
        mock_get_draft,
    )
    monkeypatch.setattr(
        "app.services.post_pipeline.content_generator.enrich_context_from_supabase",
        mock_enrich,
    )
    monkeypatch.setattr(
        "app.services.post_pipeline.content_generator.generate_post_content",
        AsyncMock(return_value=fake_contents),
    )
    monkeypatch.setattr(
        "app.services.post_pipeline.supabase_client.update_post_copy_success",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.post_pipeline.supabase_client.create_post_version",
        AsyncMock(return_value="v1"),
    )
    monkeypatch.setattr(
        "app.services.post_pipeline.supabase_client.update_job_progress",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.post_pipeline.supabase_client.complete_job",
        AsyncMock(),
    )

    await pipeline.generate_copy_batch(
        job_id="job-1",
        post_ids=post_ids,
        payload=payload,
        language="es",
    )

    assert len(enrich_calls) == 1
    assert enrich_calls[0]["brand_id"] == "my-brand-42"
    assert enrich_calls[0]["draft_id"] == "draft-123"


# ---------------------------------------------------------------------------
# 8. Job config persists full payload (not just draft config)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_config_persists_full_payload(client, monkeypatch):
    """When generating, the job config should contain the full brand/campaign
    data from the payload, not just the draft config."""
    # Mock Supabase calls for draft linkage
    mock_table = MagicMock()
    mock_table.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"config": {}}
    )
    mock_table.update.return_value.eq.return_value.execute.return_value = None

    mock_client = MagicMock()
    mock_client.table.return_value = mock_table

    monkeypatch.setattr("app.api.v1.posts.supabase_client.get_client", lambda: mock_client)

    # Track create_job calls
    create_job_calls = []

    async def mock_create_job(**kwargs):
        create_job_calls.append(kwargs)
        return "job-fake"

    monkeypatch.setattr("app.api.v1.posts.supabase_client.create_job", mock_create_job)
    monkeypatch.setattr("app.api.v1.posts.supabase_client.create_post_placeholder", AsyncMock(return_value="post-1"))
    monkeypatch.setattr("app.api.v1.posts.post_pipeline.generate_copy_batch", AsyncMock())

    payload = {
        "brand": {
            "name": "TestBrand",
            "logo_b64": "",
            "primary_color": "#FF0000",
            "secondary_color": "#00FF00",
            "accent_color": "#0000FF",
        },
        "campaign": {
            "description": "Summer sale",
            "tone": "fun",
        },
        "posts_config": [{"platform": "instagram", "format": "instagram_feed"}],
        "language": "es",
        "draft_id": "draft-1",
    }

    resp = await client.post("/api/v1/posts/generate-copy-only", json=payload)
    assert resp.status_code == 200

    assert len(create_job_calls) == 1
    config = create_job_calls[0]["config"]
    assert config is not None
    assert config["brand"]["name"] == "TestBrand"
    assert config["brand"]["primary_color"] == "#FF0000"
    assert config["campaign"]["description"] == "Summer sale"
    assert config["include_logo_in_image"] is False
    assert config["include_text_in_image"] is False
