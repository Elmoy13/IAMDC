"""Tests for the ES→EN image prompt optimizer."""

import pytest
from unittest.mock import AsyncMock

from app.services.prompt_optimizer import optimize_image_prompt


@pytest.mark.asyncio
async def test_optimize_image_prompt_basic(monkeypatch):
    """The optimizer should return an English prompt with visual keywords."""
    fake_en = (
        "Young woman enjoying a craft beer at an energetic rooftop party, "
        "warm golden hour lighting, shallow DOF, editorial photography"
    )

    async def mock_invoke_with_fallback(system_prompt, messages, **kwargs):
        return fake_en, "zai.glm-5"

    monkeypatch.setattr(
        "app.services.prompt_optimizer.bedrock.invoke_with_fallback",
        mock_invoke_with_fallback,
    )

    result = await optimize_image_prompt(
        prompt_es="Joven tomando cerveza en una fiesta",
        brand_context={"name": "CraftBeer", "tone": "fun"},
    )

    assert result == fake_en
    # Should be English (no obvious Spanish accented words)
    for word in ["cerveza", "fiesta", "Joven"]:
        assert word not in result


@pytest.mark.asyncio
async def test_optimize_prompt_preserves_brand_tone(monkeypatch):
    """For an irreverent brand, the optimized prompt should reflect the tone."""
    fake_en = (
        "Raw, unapologetic mezcal moment — someone throwing their head back "
        "in laughter, bold neon bar lighting, documentary-style 35mm film grain"
    )

    async def mock_invoke_with_fallback(system_prompt, messages, **kwargs):
        # Verify the brand tone is in the user message
        user_text = messages[0]["content"][0]["text"]
        assert "irreverente" in user_text
        return fake_en, "zai.glm-5"

    monkeypatch.setattr(
        "app.services.prompt_optimizer.bedrock.invoke_with_fallback",
        mock_invoke_with_fallback,
    )

    result = await optimize_image_prompt(
        prompt_es="Alguien riéndose fuerte con mezcal",
        brand_context={"name": "MezcalBravo", "tone": "irreverente"},
    )

    assert result == fake_en


@pytest.mark.asyncio
async def test_optimize_fallback_on_error(monkeypatch):
    """If the LLM fails, the optimizer should return the original Spanish prompt."""
    original_es = "Botella de mezcal en la playa al atardecer"

    async def mock_invoke_with_fallback(**kwargs):
        raise RuntimeError("Model unavailable")

    monkeypatch.setattr(
        "app.services.prompt_optimizer.bedrock.invoke_with_fallback",
        mock_invoke_with_fallback,
    )

    result = await optimize_image_prompt(
        prompt_es=original_es,
        brand_context={"name": "Test"},
    )

    assert result == original_es
