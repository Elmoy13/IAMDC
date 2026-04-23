"""Tests for the refactored content_generator (GLM-5 + Nova Vision)."""

import pytest
from unittest.mock import AsyncMock

from app.services.content_generator import (
    analyze_brand_visuals,
    generate_post_content,
)


@pytest.mark.asyncio
async def test_analyze_brand_visuals_skips_when_no_images(monkeypatch):
    """Without logo or product images, analyze_brand_visuals returns ''
    and does NOT call Nova Pro."""
    invoke_called = False

    async def mock_invoke_vision(**kwargs):
        nonlocal invoke_called
        invoke_called = True
        return "should not be called"

    monkeypatch.setattr(
        "app.services.content_generator.bedrock.invoke_vision",
        mock_invoke_vision,
    )

    result = await analyze_brand_visuals(logo_url=None, product_image_urls=[])

    assert result == ""
    assert not invoke_called


@pytest.mark.asyncio
async def test_analyze_brand_visuals_calls_nova_vision(monkeypatch):
    """With a logo URL, analyze_brand_visuals should call Nova Pro Vision
    and return the result."""
    expected = "Dark mezcal bottle with white label, minimal illustration."

    async def mock_invoke_vision(model_id, system, images, user_text, **kwargs):
        assert model_id == "us.amazon.nova-pro-v1:0"
        assert len(images) == 1  # just the logo
        return expected

    async def mock_fetch(url):
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake PNG

    monkeypatch.setattr(
        "app.services.content_generator.bedrock.invoke_vision",
        mock_invoke_vision,
    )
    monkeypatch.setattr(
        "app.services.content_generator._fetch_image_bytes",
        mock_fetch,
    )

    result = await analyze_brand_visuals(
        logo_url="https://example.com/logo.png",
        product_image_urls=[],
    )

    assert result == expected


@pytest.mark.asyncio
async def test_generate_post_content_uses_glm(monkeypatch):
    """generate_post_content should use invoke_with_fallback (GLM-5 first)
    and inject visual_context into the prompt."""
    import json

    captured_system = None
    captured_messages = None

    fake_response = json.dumps([
        {
            "headline": "H1",
            "body": "B1",
            "cta": "CTA1",
            "image_prompt": "IP1",
            "style_description": "bold",
        }
    ])

    async def mock_invoke_with_fallback(system_prompt, messages, **kwargs):
        nonlocal captured_system, captured_messages
        captured_system = system_prompt
        captured_messages = messages
        return fake_response, "zai.glm-5"

    monkeypatch.setattr(
        "app.services.content_generator.bedrock.invoke_with_fallback",
        mock_invoke_with_fallback,
    )

    result = await generate_post_content(
        brand_name="TestBrand",
        campaign_description="Summer sale",
        tone="fun",
        extras="",
        platform="instagram",
        format="instagram_feed",
        num_posts=1,
        brand_colors={"primary": "#FF0000", "secondary": "#00FF00", "accent": "#0000FF"},
        visual_context="Dark bottle with white label on a wooden surface.",
    )

    assert len(result) == 1
    assert result[0]["headline"] == "H1"
    assert result[0]["image_prompt"] == "IP1"

    # Visual context should appear in the user message sent to GLM
    user_text = captured_messages[0]["content"][0]["text"]
    assert "Dark bottle with white label" in user_text
