"""Tests for app.services.template_generator.

All AWS / Bedrock calls are mocked so the suite runs entirely offline.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.template_generator import (
    FORMAT_DIMENSIONS,
    _BG_PLACEHOLDER,
    _LOGO_PLACEHOLDER,
    _build_prompt,
    _post_process,
    generate_post_template,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BRAND = {
    "primary_color": "#E63946",
    "secondary_color": "#1D3557",
    "accent_color": "#F1FAEE",
    "font_family": "Montserrat",
    "logo_b64": "",
}

COPY = {
    "headline": "Despierta tus sentidos",
    "body": "Café de origen único, tostado artesanal",
    "cta": "Pruébalo hoy →",
}

VALID_HTML = "<!DOCTYPE html><html><head></head><body>ok</body></html>"


def _make_bedrock_response(text: str) -> dict:
    """Simulate the dict returned by boto3 invoke_model."""
    body_bytes = json.dumps(
        {"output": {"message": {"content": [{"text": text}]}}}
    ).encode()
    mock_stream = MagicMock()
    mock_stream.read.return_value = body_bytes
    return {"body": mock_stream}


# ---------------------------------------------------------------------------
# Unit tests — pure logic (no I/O)
# ---------------------------------------------------------------------------


def test_format_dimensions_contains_all_formats():
    expected = {"instagram_feed", "instagram_story", "facebook_post", "linkedin_post"}
    assert set(FORMAT_DIMENSIONS.keys()) == expected


def test_build_prompt_contains_copy():
    prompt = _build_prompt("instagram_feed", BRAND, COPY, "elegante", has_logo=False)
    assert "Despierta tus sentidos" in prompt
    assert "Café de origen único" in prompt
    assert "Pruébalo hoy →" in prompt


def test_build_prompt_contains_bg_placeholder():
    prompt = _build_prompt("instagram_feed", BRAND, COPY, "elegante", has_logo=False)
    assert _BG_PLACEHOLDER in prompt


def test_build_prompt_logo_rule_without_logo():
    prompt = _build_prompt("instagram_feed", BRAND, COPY, "elegante", has_logo=False)
    assert "no logo" in prompt.lower() or "no hay logo" in prompt.lower() or "There is no logo" in prompt


def test_build_prompt_logo_rule_with_logo():
    prompt = _build_prompt("instagram_feed", BRAND, COPY, "elegante", has_logo=True)
    assert _LOGO_PLACEHOLDER in prompt


def test_build_prompt_dimensions_instagram_feed():
    prompt = _build_prompt("instagram_feed", BRAND, COPY, "elegante", has_logo=False)
    assert "1080" in prompt


def test_build_prompt_dimensions_instagram_story():
    prompt = _build_prompt("instagram_story", BRAND, COPY, "elegante", has_logo=False)
    assert "1920" in prompt


def test_build_prompt_includes_brand_colors():
    prompt = _build_prompt("instagram_feed", BRAND, COPY, "elegante", has_logo=False)
    assert "#E63946" in prompt
    assert "#1D3557" in prompt


def test_build_prompt_includes_style():
    prompt = _build_prompt("instagram_feed", BRAND, COPY, "divertido y juvenil", has_logo=False)
    assert "divertido y juvenil" in prompt


def test_post_process_substitutes_background():
    raw = f"<!DOCTYPE html><html><body><img src='{_BG_PLACEHOLDER}'></body></html>"
    result = _post_process(raw, "data:image/png;base64,ABC123", "")
    assert "data:image/png;base64,ABC123" in result
    assert _BG_PLACEHOLDER not in result


def test_post_process_substitutes_logo():
    raw = f"<!DOCTYPE html><html><body><img src='{_LOGO_PLACEHOLDER}'></body></html>"
    result = _post_process(raw, "data:image/png;base64,BG", "data:image/png;base64,LOGO")
    assert "data:image/png;base64,LOGO" in result
    assert _LOGO_PLACEHOLDER not in result


def test_post_process_strips_markdown_fences():
    raw = "```html\n<!DOCTYPE html><html><body></body></html>\n```"
    result = _post_process(raw, "data:image/png;base64,X", "")
    assert "```" not in result
    assert result.lower().startswith("<!doctype")


def test_post_process_no_logo_url_leaves_placeholder():
    """When logo_data_url is empty, LOGO_PLACEHOLDER stays (shouldn't be in HTML anyway)."""
    raw = f"<!DOCTYPE html><html><body>no logo here</body></html>"
    result = _post_process(raw, "data:image/png;base64,BG", "")
    assert _LOGO_PLACEHOLDER not in result  # was never in raw


# ---------------------------------------------------------------------------
# Async integration tests — boto3 mocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_post_template_returns_html():
    mock_response = _make_bedrock_response(VALID_HTML)

    with patch(
        "app.services.template_generator._get_bedrock_client"
    ) as mock_factory:
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = mock_response
        mock_factory.return_value = mock_client

        result = await generate_post_template(
            format="instagram_feed",
            brand=BRAND,
            copy=COPY,
            style_description="elegante",
            background_image_b64="data:image/png;base64,FAKEBASE64",
        )

    assert result.lower().startswith("<!doctype")
    mock_client.invoke_model.assert_called_once()


@pytest.mark.asyncio
async def test_generate_post_template_injects_bg_data_url():
    html_with_placeholder = (
        f"<!DOCTYPE html><html><body>"
        f"<img src='{_BG_PLACEHOLDER}'></body></html>"
    )
    mock_response = _make_bedrock_response(html_with_placeholder)

    with patch(
        "app.services.template_generator._get_bedrock_client"
    ) as mock_factory:
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = mock_response
        mock_factory.return_value = mock_client

        result = await generate_post_template(
            format="instagram_feed",
            brand=BRAND,
            copy=COPY,
            style_description="elegante",
            background_image_b64="RAWBASE64DATA",
        )

    assert "data:image/png;base64,RAWBASE64DATA" in result
    assert _BG_PLACEHOLDER not in result


@pytest.mark.asyncio
async def test_generate_post_template_raises_for_unsupported_format():
    with pytest.raises(ValueError, match="Unsupported format"):
        await generate_post_template(
            format="tiktok_video",
            brand=BRAND,
            copy=COPY,
            style_description="cualquiera",
            background_image_b64="data:image/png;base64,X",
        )


@pytest.mark.asyncio
async def test_generate_post_template_retries_on_invalid_html():
    """First call returns garbage; second call returns valid HTML — should succeed."""
    garbage_response = _make_bedrock_response("This is not HTML at all.")
    valid_response = _make_bedrock_response(VALID_HTML)

    with patch(
        "app.services.template_generator._get_bedrock_client"
    ) as mock_factory:
        mock_client = MagicMock()
        mock_client.invoke_model.side_effect = [garbage_response, valid_response]
        mock_factory.return_value = mock_client

        result = await generate_post_template(
            format="facebook_post",
            brand=BRAND,
            copy=COPY,
            style_description="moderno",
            background_image_b64="data:image/png;base64,X",
        )

    assert result.lower().startswith("<!doctype")
    assert mock_client.invoke_model.call_count == 2


@pytest.mark.asyncio
async def test_generate_post_template_raises_after_max_retries():
    """Both attempts return invalid HTML → RuntimeError."""
    garbage = _make_bedrock_response("not html")

    with patch(
        "app.services.template_generator._get_bedrock_client"
    ) as mock_factory:
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = garbage
        mock_factory.return_value = mock_client

        with pytest.raises(RuntimeError, match="Template generation failed"):
            await generate_post_template(
                format="linkedin_post",
                brand=BRAND,
                copy=COPY,
                style_description="profesional",
                background_image_b64="data:image/png;base64,X",
            )

    assert mock_client.invoke_model.call_count == 2  # initial + 1 retry


@pytest.mark.asyncio
async def test_generate_post_template_calls_correct_bedrock_model(monkeypatch):
    """invoke_model must receive the template_model_id from settings."""
    monkeypatch.setattr("app.config.settings.template_model_id", "amazon.nova-pro-v1:0")

    mock_response = _make_bedrock_response(VALID_HTML)

    with patch(
        "app.services.template_generator._get_bedrock_client"
    ) as mock_factory:
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = mock_response
        mock_factory.return_value = mock_client

        await generate_post_template(
            format="instagram_feed",
            brand=BRAND,
            copy=COPY,
            style_description="elegante",
            background_image_b64="data:image/png;base64,X",
        )

    call_kwargs = mock_client.invoke_model.call_args
    assert call_kwargs.kwargs["modelId"] == "amazon.nova-pro-v1:0"


@pytest.mark.asyncio
async def test_generate_post_template_bedrock_exception_raises_runtime_error():
    """A boto3 exception on every attempt must surface as RuntimeError."""
    with patch(
        "app.services.template_generator._get_bedrock_client"
    ) as mock_factory:
        mock_client = MagicMock()
        mock_client.invoke_model.side_effect = Exception("Connection refused")
        mock_factory.return_value = mock_client

        with pytest.raises(RuntimeError, match="Template generation failed"):
            await generate_post_template(
                format="instagram_feed",
                brand=BRAND,
                copy=COPY,
                style_description="elegante",
                background_image_b64="data:image/png;base64,X",
            )
