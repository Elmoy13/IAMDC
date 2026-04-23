import base64
import colorsys
import io

from colorthief import ColorThief
from PIL import Image

from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _luminance_simple(rgb: tuple[int, int, int]) -> float:
    """Simple perceived luminance (fast, good enough for bg suggestion)."""
    r, g, b = rgb
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _luminance_wcag(rgb: tuple[int, int, int]) -> float:
    """Relative luminance per WCAG 2.1 — used for contrast_color decision."""
    def _ch(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)


def _is_near_white(rgb: tuple[int, int, int], threshold: int = 225) -> bool:
    return all(c >= threshold for c in rgb)


def _is_near_black(rgb: tuple[int, int, int], threshold: int = 30) -> bool:
    return all(c <= threshold for c in rgb)


def _is_neutral(rgb: tuple[int, int, int]) -> bool:
    if _is_near_white(rgb) or _is_near_black(rgb):
        return True
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    # Very low saturation at high/low brightness → grey tones
    return s < 0.10 and (v > 0.85 or v < 0.15)


def _suggest_fonts(palette_rgb: list[tuple[int, int, int]]) -> list[str]:
    """Hue-based font suggestion using the top-3 palette colors."""
    top = palette_rgb[:3]
    avg_hue = 0.0
    avg_sat = 0.0
    for rgb in top:
        h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
        avg_hue += h
        avg_sat += s
    avg_hue /= len(top)
    avg_sat /= len(top)

    if avg_sat < 0.3:
        return ["Inter", "Space Grotesk", "DM Sans"]
    if avg_hue < 0.1 or avg_hue > 0.9:      # reds
        return ["Montserrat", "Poppins", "Raleway"]
    if avg_hue < 0.2:                         # oranges / yellows
        return ["Poppins", "Nunito", "Quicksand"]
    if avg_hue < 0.45:                        # greens
        return ["Lora", "Merriweather", "Source Serif Pro"]
    if avg_hue < 0.7:                         # blues
        return ["Playfair Display", "Montserrat", "Roboto"]
    # purples / pinks
    return ["Playfair Display", "Cormorant Garamond", "Libre Baskerville"]


def _open_with_pil_fallback(image_bytes: bytes) -> io.BytesIO:
    """Convert any PIL-supported format to RGB PNG in a BytesIO buffer."""
    buf_in = io.BytesIO(image_bytes)
    try:
        img = Image.open(buf_in).convert("RGB")
        buf_out = io.BytesIO()
        img.save(buf_out, format="PNG")
        buf_out.seek(0)
        return buf_out
    except Exception:
        buf_in.seek(0)
        return buf_in


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def analyze_brand_from_logo(logo_b64: str) -> dict:
    """Extract brand palette and metadata from a logo.

    Args:
        logo_b64: Logo as a raw base64 string or data URL (with/without prefix).

    Returns:
        Brand profile dict with primary_color, secondary_color, accent_color,
        palette, background_suggestion, contrast_color, and suggested_fonts.
    """
    if "," in logo_b64:
        logo_b64 = logo_b64.split(",", 1)[1]

    logo_bytes = base64.b64decode(logo_b64)

    # ColorThief works best with a clean RGB PNG; use PIL as a pre-converter
    buf = _open_with_pil_fallback(logo_bytes)

    ct = ColorThief(buf)
    raw_palette: list[tuple[int, int, int]] = ct.get_palette(color_count=8, quality=1)

    # Filter neutrals; fall back to raw if everything gets filtered out
    filtered = [c for c in raw_palette if not _is_neutral(c)]
    if len(filtered) < 3:
        filtered = list(raw_palette[:5])

    palette_rgb = filtered[:5]

    # Pad to 5 colors if needed
    for c in raw_palette:
        if len(palette_rgb) >= 5:
            break
        if c not in palette_rgb:
            palette_rgb.append(c)

    primary   = palette_rgb[0]
    secondary = palette_rgb[1] if len(palette_rgb) > 1 else (200, 200, 200)
    accent    = palette_rgb[2] if len(palette_rgb) > 2 else (128, 128, 128)

    palette_hex = [_rgb_to_hex(c) for c in palette_rgb]

    lum_simple = _luminance_simple(primary)
    bg_suggestion  = "light" if lum_simple > 0.5 else "dark"
    contrast_color = "#000000" if lum_simple > 0.5 else "#FFFFFF"

    logger.info(
        "brand_analyzed",
        primary=_rgb_to_hex(primary),
        bg_suggestion=bg_suggestion,
    )

    return {
        "primary_color":         _rgb_to_hex(primary),
        "secondary_color":       _rgb_to_hex(secondary),
        "accent_color":          _rgb_to_hex(accent),
        "palette":               palette_hex,
        "background_suggestion": bg_suggestion,
        "contrast_color":        contrast_color,
        "suggested_fonts":       _suggest_fonts(palette_rgb),
    }
