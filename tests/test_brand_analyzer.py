"""Tests for app.services.brand_analyzer.

All tests are offline — no network calls needed.
A minimal 2×2 solid-color PNG is generated in-memory for each test.
"""

import base64
import io

import pytest
from PIL import Image

from app.services.brand_analyzer import (
    _is_neutral,
    _luminance_simple,
    _rgb_to_hex,
    _suggest_fonts,
    analyze_brand_from_logo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _solid_png_b64(rgb: tuple[int, int, int], size: int = 50) -> str:
    """Create a small solid-color PNG and return it as raw base64."""
    img = Image.new("RGB", (size, size), rgb)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _data_url_png(rgb: tuple[int, int, int]) -> str:
    return f"data:image/png;base64,{_solid_png_b64(rgb)}"


# ---------------------------------------------------------------------------
# Unit tests — pure helpers
# ---------------------------------------------------------------------------


def test_rgb_to_hex_red():
    assert _rgb_to_hex((255, 0, 0)) == "#FF0000"


def test_rgb_to_hex_white():
    assert _rgb_to_hex((255, 255, 255)) == "#FFFFFF"


def test_rgb_to_hex_black():
    assert _rgb_to_hex((0, 0, 0)) == "#000000"


def test_rgb_to_hex_arbitrary():
    assert _rgb_to_hex((230, 57, 70)) == "#E63946"


def test_luminance_simple_white_is_one():
    assert abs(_luminance_simple((255, 255, 255)) - 1.0) < 0.001


def test_luminance_simple_black_is_zero():
    assert _luminance_simple((0, 0, 0)) == 0.0


def test_luminance_simple_mid_grey():
    lum = _luminance_simple((128, 128, 128))
    assert 0.4 < lum < 0.6


def test_is_neutral_white():
    assert _is_neutral((255, 255, 255)) is True


def test_is_neutral_black():
    assert _is_neutral((0, 0, 0)) is True


def test_is_neutral_grey():
    assert _is_neutral((240, 240, 240)) is True


def test_is_neutral_vibrant_red():
    assert _is_neutral((230, 57, 70)) is False


def test_is_neutral_vibrant_blue():
    assert _is_neutral((29, 53, 87)) is False


def test_suggest_fonts_low_saturation():
    # Near-grey palette → clean / tech fonts
    grey = [(150, 150, 150), (160, 160, 160), (140, 140, 140)]
    fonts = _suggest_fonts(grey)
    assert any(f in fonts for f in ["Inter", "Space Grotesk", "DM Sans"])


def test_suggest_fonts_red():
    red = [(230, 30, 30), (200, 20, 20), (210, 25, 25)]
    fonts = _suggest_fonts(red)
    assert any(f in fonts for f in ["Montserrat", "Poppins", "Raleway"])


def test_suggest_fonts_blue():
    blue = [(29, 53, 180), (20, 60, 200), (30, 50, 170)]
    fonts = _suggest_fonts(blue)
    assert any(f in fonts for f in ["Playfair Display", "Montserrat", "Roboto"])


def test_suggest_fonts_green():
    green = [(30, 150, 60), (20, 130, 50), (40, 160, 70)]
    fonts = _suggest_fonts(green)
    assert any(f in fonts for f in ["Lora", "Merriweather", "Source Serif Pro"])


def test_suggest_fonts_returns_three():
    palette = [(230, 57, 70), (29, 53, 87), (241, 250, 238)]
    assert len(_suggest_fonts(palette)) == 3


# ---------------------------------------------------------------------------
# Async integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_returns_all_keys():
    result = await analyze_brand_from_logo(_solid_png_b64((230, 57, 70)))
    required = {
        "primary_color", "secondary_color", "accent_color",
        "palette", "background_suggestion", "contrast_color", "suggested_fonts",
    }
    assert required <= result.keys()


@pytest.mark.asyncio
async def test_analyze_primary_color_is_hex():
    result = await analyze_brand_from_logo(_solid_png_b64((230, 57, 70)))
    pc = result["primary_color"]
    assert pc.startswith("#") and len(pc) == 7


@pytest.mark.asyncio
async def test_analyze_palette_has_up_to_five():
    result = await analyze_brand_from_logo(_solid_png_b64((29, 53, 87)))
    assert 1 <= len(result["palette"]) <= 5


@pytest.mark.asyncio
async def test_analyze_background_suggestion_valid_values():
    result = await analyze_brand_from_logo(_solid_png_b64((230, 57, 70)))
    assert result["background_suggestion"] in ("light", "dark")


@pytest.mark.asyncio
async def test_analyze_contrast_color_valid():
    result = await analyze_brand_from_logo(_solid_png_b64((230, 57, 70)))
    assert result["contrast_color"] in ("#000000", "#FFFFFF")


@pytest.mark.asyncio
async def test_analyze_suggested_fonts_is_list_of_three():
    result = await analyze_brand_from_logo(_solid_png_b64((100, 149, 237)))
    assert isinstance(result["suggested_fonts"], list)
    assert len(result["suggested_fonts"]) == 3


@pytest.mark.asyncio
async def test_analyze_accepts_data_url():
    """Should strip the data:image/png;base64, prefix transparently."""
    result = await analyze_brand_from_logo(_data_url_png((50, 100, 200)))
    assert result["primary_color"].startswith("#")


@pytest.mark.asyncio
async def test_analyze_light_color_gives_dark_background():
    """A bright yellow logo → background_suggestion should be 'light'
    (light background for a bright primary)."""
    result = await analyze_brand_from_logo(_solid_png_b64((255, 220, 50)))
    assert result["background_suggestion"] == "light"
    assert result["contrast_color"] == "#000000"


@pytest.mark.asyncio
async def test_analyze_dark_color_gives_light_background():
    """A dark navy logo → background_suggestion should be 'dark'."""
    result = await analyze_brand_from_logo(_solid_png_b64((10, 20, 60)))
    assert result["background_suggestion"] == "dark"
    assert result["contrast_color"] == "#FFFFFF"
