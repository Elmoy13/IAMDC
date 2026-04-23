"""Build NexusAI slide-deck JSON from AI-generated slide content + searched images.

The slide_content comes from the AI Slide Director (Pass 2) and contains:
  - title, subtitle, body_items, image_query, layout per slide.
The image_map contains slide_number → image_url from Unsplash.
The brand dict contains colors, name, logo_url, etc.
"""
import time
import uuid
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def _uid() -> str:
    return f"el-{int(time.time() * 1000)}-{uuid.uuid4().hex[:4]}"


def _slide_id(idx: int) -> str:
    return f"1-{idx}"


# ── Layout engines ─────────────────────────────────────────

def _layout_hero(slide: dict, img_url: str, colors: dict, logo_url: str | None) -> list[dict]:
    """Full background image + big title + subtitle overlay."""
    elements: list[dict] = []
    if img_url:
        elements.append({
            "id": _uid(), "type": "image", "content": img_url,
            "x": 0, "y": 0, "width": 1920, "height": 1080,
            "opacity": 0.65, "zIndex": 0,
        })
    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", ""),
        "x": 80, "y": 620, "width": 1760, "height": 160,
        "fontSize": 96, "fontWeight": "900", "color": "#ffffff",
        "zIndex": 1,
    })
    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 80, "y": 800, "width": 1400, "height": 70,
            "fontSize": 30, "fontWeight": "400", "color": "rgba(255,255,255,0.6)",
            "zIndex": 2,
        })
    if logo_url:
        elements.append({
            "id": _uid(), "type": "image", "content": logo_url,
            "x": 1650, "y": 40, "width": 210, "height": 210,
            "zIndex": 3,
        })
    return elements


def _layout_split_left(slide: dict, img_url: str, colors: dict, logo_url: str | None) -> list[dict]:
    """Image on left, text content on right."""
    elements: list[dict] = []
    text_dark = colors.get("secondary", "#0F172A")
    text_muted = "#475569"

    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", ""),
        "x": 860, "y": 80, "width": 980, "height": 90,
        "fontSize": 56, "fontWeight": "800", "color": text_dark,
        "zIndex": 0,
    })
    if img_url:
        elements.append({
            "id": _uid(), "type": "image", "content": img_url,
            "x": 60, "y": 80, "width": 720, "height": 920,
            "zIndex": 1,
        })
    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 860, "y": 180, "width": 980, "height": 60,
            "fontSize": 24, "fontWeight": "400", "color": "#64748b",
            "zIndex": 2,
        })
    body_items = slide.get("body_items", [])
    for i, item in enumerate(body_items[:5]):
        elements.append({
            "id": _uid(), "type": "text", "content": f"→  {item}",
            "x": 860, "y": 280 + i * 130, "width": 980, "height": 110,
            "fontSize": 26, "fontWeight": "400", "color": text_muted,
            "zIndex": 3 + i,
        })
    return elements


def _layout_split_right(slide: dict, img_url: str, colors: dict, logo_url: str | None) -> list[dict]:
    """Text on left, image on right."""
    elements: list[dict] = []
    text_dark = colors.get("secondary", "#0F172A")
    text_muted = "#475569"

    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", ""),
        "x": 80, "y": 80, "width": 980, "height": 90,
        "fontSize": 56, "fontWeight": "800", "color": text_dark,
        "zIndex": 0,
    })
    if img_url:
        elements.append({
            "id": _uid(), "type": "image", "content": img_url,
            "x": 1140, "y": 80, "width": 720, "height": 920,
            "zIndex": 1,
        })
    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 80, "y": 180, "width": 980, "height": 60,
            "fontSize": 24, "fontWeight": "400", "color": "#64748b",
            "zIndex": 2,
        })
    body_items = slide.get("body_items", [])
    for i, item in enumerate(body_items[:5]):
        elements.append({
            "id": _uid(), "type": "text", "content": f"→  {item}",
            "x": 80, "y": 280 + i * 130, "width": 980, "height": 110,
            "fontSize": 26, "fontWeight": "400", "color": text_muted,
            "zIndex": 3 + i,
        })
    return elements


def _layout_three_columns(slide: dict, img_url: str, colors: dict, logo_url: str | None) -> list[dict]:
    """Title + 3 color cards with body items."""
    elements: list[dict] = []
    primary = colors.get("primary", "#06B6D4")
    text_dark = colors.get("secondary", "#0F172A")

    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", ""),
        "x": 80, "y": 60, "width": 1760, "height": 90,
        "fontSize": 56, "fontWeight": "800", "color": text_dark,
        "zIndex": 0,
    })
    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 80, "y": 155, "width": 1760, "height": 50,
            "fontSize": 24, "fontWeight": "400", "color": "#64748b",
            "zIndex": 1,
        })

    body_items = slide.get("body_items", [])
    col_width = 550
    gap = 45
    start_x = 80
    for i in range(min(len(body_items), 3)):
        x = start_x + i * (col_width + gap)
        # Card background
        elements.append({
            "id": _uid(), "type": "shape", "content": primary,
            "x": x, "y": 240, "width": col_width, "height": 750,
            "zIndex": 2 + i * 2,
        })
        # Card text
        elements.append({
            "id": _uid(), "type": "text", "content": body_items[i],
            "x": x + 30, "y": 280, "width": col_width - 60, "height": 680,
            "fontSize": 24, "fontWeight": "500", "color": "#ffffff",
            "zIndex": 3 + i * 2,
        })

    return elements


def _layout_art_direction(slide: dict, img_url: str, colors: dict, logo_url: str | None) -> list[dict]:
    """Moodboard image + color swatches + brand tones."""
    elements: list[dict] = []
    text_dark = colors.get("secondary", "#0F172A")
    text_muted = "#475569"
    text_light = "#64748b"

    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", "Dirección de Arte"),
        "x": 80, "y": 60, "width": 1000, "height": 90,
        "fontSize": 56, "fontWeight": "800", "color": text_dark,
        "zIndex": 0,
    })
    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 80, "y": 160, "width": 1000, "height": 55,
            "fontSize": 28, "fontWeight": "400", "color": text_light,
            "zIndex": 1,
        })
    if img_url:
        elements.append({
            "id": _uid(), "type": "image", "content": img_url,
            "x": 80, "y": 260, "width": 1020, "height": 720,
            "zIndex": 2,
        })

    # Color swatches
    color_pairs = [
        (colors.get("primary", "#06B6D4"), "Primary"),
        (colors.get("secondary", "#0F172A"), "Secondary"),
        (colors.get("neutral", "#E2E8F0"), "Neutral"),
        (colors.get("accent", "#14B8A6"), "Accent"),
    ]
    for i, (hex_c, label) in enumerate(color_pairs):
        col = 1200 + (i % 2) * 200
        row = 260 + (i // 2) * 220
        elements.append({
            "id": _uid(), "type": "shape", "content": hex_c,
            "x": col, "y": row, "width": 170, "height": 170,
            "zIndex": 3 + i * 2,
        })
        elements.append({
            "id": _uid(), "type": "text", "content": f"{label}\n{hex_c}",
            "x": col, "y": row + 180, "width": 190, "height": 50,
            "fontSize": 16, "fontWeight": "500", "color": text_muted,
            "zIndex": 4 + i * 2,
        })

    if logo_url:
        elements.append({
            "id": _uid(), "type": "image", "content": logo_url,
            "x": 1200, "y": 750, "width": 370, "height": 170,
            "zIndex": 20,
        })
    return elements


def _layout_full_bg(slide: dict, img_url: str, colors: dict, logo_url: str | None) -> list[dict]:
    """Full color background with centered text (CTA/close slide)."""
    elements: list[dict] = []
    primary = colors.get("primary", "#06B6D4")

    elements.append({
        "id": _uid(), "type": "shape", "content": primary,
        "x": 0, "y": 0, "width": 1920, "height": 1080,
        "zIndex": 0,
    })
    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", ""),
        "x": 80, "y": 300, "width": 1760, "height": 160,
        "fontSize": 96, "fontWeight": "900", "color": "#ffffff",
        "zIndex": 1,
    })
    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 80, "y": 490, "width": 1760, "height": 80,
            "fontSize": 36, "fontWeight": "400", "color": "rgba(255,255,255,0.7)",
            "zIndex": 2,
        })
    if logo_url:
        elements.append({
            "id": _uid(), "type": "image", "content": logo_url,
            "x": 760, "y": 640, "width": 400, "height": 300,
            "zIndex": 3,
        })
    return elements


LAYOUT_MAP = {
    "hero": _layout_hero,
    "split-left": _layout_split_left,
    "split-right": _layout_split_right,
    "three-columns": _layout_three_columns,
    "grid-2x2": _layout_split_left,  # fallback
    "full-bg": _layout_full_bg,
}

# Map slide types
SLIDE_TYPE_MAP = {
    1: "cover",
    2: "content",
    3: "content",
    4: "art",
    5: "content",
    6: "cover",
}


def build_presentation(
    brand: dict,
    slide_content: list[dict],
    image_map: dict[int, str],
) -> list[dict]:
    """Build the final slide-deck JSON from AI content + real images.

    Args:
        brand: Brand data (name, colors, logo_url, etc.)
        slide_content: AI-generated list of slide dicts from Pass 2
        image_map: {slide_number: unsplash_url}
    """
    colors = brand.get("colors", {})
    logo_url = brand.get("logo_url")

    slides: list[dict] = []

    for i, sc in enumerate(slide_content):
        num = sc.get("slide_number", i + 1)
        layout = sc.get("layout", "split-left")
        img_url = image_map.get(num, "")

        # Special override: art direction slide always uses the art layout
        slide_type_str = sc.get("type", SLIDE_TYPE_MAP.get(num, "content"))
        if slide_type_str == "art" or num == 4:
            layout = "art"

        # Pick layout function
        if layout == "art":
            elements = _layout_art_direction(sc, img_url, colors, logo_url)
        else:
            layout_fn = LAYOUT_MAP.get(layout, _layout_split_left)
            elements = layout_fn(sc, img_url, colors, logo_url)

        # Determine slide bg
        bg = "#ffffff"
        if layout == "full-bg":
            bg = colors.get("primary", "#06B6D4")

        slides.append({
            "id": _slide_id(num),
            "type": slide_type_str,
            "backgroundColor": bg,
            "transition": "fade",
            "image": img_url if layout == "hero" else "",
            "elements": elements,
        })

    logger.info("presentation_built", slides=len(slides), brand=brand.get("name"))
    return slides
