"""Build NexusAI slide-deck JSON from AI-generated slide content + searched images.

V2 — Uses structured templates, rotates brand palette, and produces
balanced layouts for every slide type.
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


# ── Palette helpers ────────────────────────────────────────

def _build_palette(colors: dict) -> dict:
    """Normalise whatever colour dict the agent provides into a usable palette."""
    accents_raw = colors.get("accents", {})
    if isinstance(accents_raw, dict):
        accent_list = list(accents_raw.values())
    elif isinstance(accents_raw, list):
        accent_list = accents_raw
    else:
        accent_list = []

    palette = {
        "primary": colors.get("primary", "#2563EB"),
        "background": colors.get("background", "#FAFAFA"),
        "foreground": colors.get("foreground", colors.get("neutral", "#161B26")),
        "secondary": colors.get("secondary", "#0F172A"),
        "accent": colors.get("accent", accent_list[0] if accent_list else "#14B8A6"),
        "accents": accent_list or [colors.get("accent", "#14B8A6")],
    }
    return palette


def _rotate_accent(palette: dict, index: int) -> str:
    """Pick an accent colour, rotating through available accents."""
    accents = palette["accents"]
    if not accents:
        return palette["primary"]
    return accents[index % len(accents)]


def _text_on_bg(palette: dict, bg: str) -> str:
    """Choose foreground or background colour for text depending on bg luminance."""
    from app.services.slide_postprocess import _relative_luminance, _hex_to_rgb
    lum = _relative_luminance(_hex_to_rgb(bg))
    if lum > 0.5:
        return palette["foreground"]
    return palette["background"]


def _muted_text(palette: dict) -> str:
    """A muted/secondary text colour."""
    return "#475569"


# ── Layout templates ───────────────────────────────────────
# Each returns list[dict] of elements.
# Canvas: 1920 × 1080.

def _layout_cover(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Hero image + title + tagline + logo. bg = dark overlay."""
    bg = "#0F172A"
    elements: list[dict] = []

    if img_url:
        elements.append({
            "id": _uid(), "type": "image", "content": img_url,
            "x": 0, "y": 0, "width": 1920, "height": 1080,
            "opacity": 0.55, "zIndex": 0,
        })

    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", ""),
        "x": 80, "y": 580, "width": 1760, "height": 180,
        "fontSize": 96, "fontWeight": "900", "color": "#FAFAFA",
        "zIndex": 1,
    })

    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 80, "y": 780, "width": 1400, "height": 70,
            "fontSize": 30, "fontWeight": "400", "color": "rgba(255,255,255,0.65)",
            "zIndex": 2,
        })

    if logo_url:
        elements.append({
            "id": _uid(), "type": "image", "content": logo_url,
            "x": 1650, "y": 40, "width": 210, "height": 210,
            "zIndex": 3,
        })

    return elements, bg


def _layout_split_50_50(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Image left 50%, text content right 50%."""
    bg = palette["background"]
    title_color = palette["foreground"]
    bullet_accent = palette["primary"]
    elements: list[dict] = []

    if img_url:
        elements.append({
            "id": _uid(), "type": "image", "content": img_url,
            "x": 0, "y": 0, "width": 920, "height": 1080,
            "zIndex": 0,
        })

    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", ""),
        "x": 990, "y": 80, "width": 860, "height": 100,
        "fontSize": 48, "fontWeight": "800", "color": title_color,
        "zIndex": 1,
    })

    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 990, "y": 190, "width": 860, "height": 60,
            "fontSize": 22, "fontWeight": "400", "color": _muted_text(palette),
            "zIndex": 2,
        })

    body_items = slide.get("body_items", [])
    y_start = 290
    for i, item in enumerate(body_items[:6]):
        elements.append({
            "id": _uid(), "type": "text", "content": f"→  {item}",
            "x": 990, "y": y_start + i * 110, "width": 860, "height": 95,
            "fontSize": 24, "fontWeight": "400", "color": _muted_text(palette),
            "zIndex": 3 + i,
        })

    return elements, bg


def _layout_split_with_bullets(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Title top + bullet points distributed symmetrically, optional image right."""
    bg = palette["background"]
    title_color = palette["foreground"]
    elements: list[dict] = []

    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", ""),
        "x": 80, "y": 60, "width": 1760, "height": 100,
        "fontSize": 56, "fontWeight": "800", "color": title_color,
        "zIndex": 0,
    })

    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 80, "y": 170, "width": 1760, "height": 55,
            "fontSize": 24, "fontWeight": "400", "color": _muted_text(palette),
            "zIndex": 1,
        })

    body_items = slide.get("body_items", [])
    col_width = 860 if img_url else 1760
    y_start = 270
    for i, item in enumerate(body_items[:5]):
        # Accent-coloured bullet marker
        elements.append({
            "id": _uid(), "type": "shape", "content": _rotate_accent(palette, i),
            "x": 80, "y": y_start + i * 130 + 8, "width": 12, "height": 12,
            "zIndex": 2 + i * 2,
        })
        elements.append({
            "id": _uid(), "type": "text", "content": item,
            "x": 110, "y": y_start + i * 130, "width": col_width, "height": 110,
            "fontSize": 26, "fontWeight": "400", "color": _muted_text(palette),
            "zIndex": 3 + i * 2,
        })

    if img_url:
        elements.append({
            "id": _uid(), "type": "image", "content": img_url,
            "x": 1040, "y": 250, "width": 820, "height": 750,
            "zIndex": 20,
        })
    # Constrain title width when image is present
    if img_url:
        for el in elements:
            if el.get("type") == "text" and el.get("width", 0) > 1200:
                el["width"] = 900

    return elements, bg


def _layout_three_cards(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Title + 3 equal-width cards, each a different colour from the palette."""
    bg = palette["background"]
    title_color = palette["foreground"]
    elements: list[dict] = []

    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", ""),
        "x": 80, "y": 60, "width": 1760, "height": 100,
        "fontSize": 56, "fontWeight": "800", "color": title_color,
        "zIndex": 0,
    })

    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 80, "y": 165, "width": 1760, "height": 50,
            "fontSize": 24, "fontWeight": "400", "color": _muted_text(palette),
            "zIndex": 1,
        })

    body_items = slide.get("body_items", [])
    card_colors = [
        palette["primary"],
        _rotate_accent(palette, 0),
        _rotate_accent(palette, 1),
    ]

    col_width = 550
    gap = 45
    start_x = 80
    card_y = 250
    card_h = 740

    for i in range(min(len(body_items), 3)):
        x = start_x + i * (col_width + gap)
        card_bg = card_colors[i % len(card_colors)]

        # Card shape
        elements.append({
            "id": _uid(), "type": "shape", "content": card_bg,
            "x": x, "y": card_y, "width": col_width, "height": card_h,
            "zIndex": 2 + i * 3,
        })

        # Card number
        elements.append({
            "id": _uid(), "type": "text",
            "content": f"0{i + 1}",
            "x": x + 30, "y": card_y + 30, "width": 100, "height": 70,
            "fontSize": 48, "fontWeight": "900", "color": "rgba(255,255,255,0.3)",
            "zIndex": 3 + i * 3,
        })

        # Card body text
        elements.append({
            "id": _uid(), "type": "text", "content": body_items[i],
            "x": x + 30, "y": card_y + 120, "width": col_width - 60, "height": card_h - 160,
            "fontSize": 24, "fontWeight": "500", "color": "#ffffff",
            "zIndex": 4 + i * 3,
        })

    return elements, bg


def _layout_big_quote(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Single big quote/phrase centred on the slide."""
    bg = palette["foreground"]  # dark background
    elements: list[dict] = []

    elements.append({
        "id": _uid(), "type": "text",
        "content": "\"",
        "x": 80, "y": 200, "width": 200, "height": 200,
        "fontSize": 240, "fontWeight": "900", "color": palette["primary"],
        "zIndex": 0,
    })

    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", ""),
        "x": 160, "y": 340, "width": 1600, "height": 260,
        "fontSize": 56, "fontWeight": "700", "color": palette["background"],
        "zIndex": 1,
    })

    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 160, "y": 640, "width": 1600, "height": 80,
            "fontSize": 28, "fontWeight": "400", "color": "rgba(255,255,255,0.6)",
            "zIndex": 2,
        })

    return elements, bg


def _layout_color_palette(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Art direction slide — moodboard image + palette swatches + labels."""
    bg = palette["background"]
    title_color = palette["foreground"]
    elements: list[dict] = []

    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", "Dirección de Arte"),
        "x": 80, "y": 60, "width": 1000, "height": 90,
        "fontSize": 56, "fontWeight": "800", "color": title_color,
        "zIndex": 0,
    })

    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 80, "y": 160, "width": 1000, "height": 55,
            "fontSize": 24, "fontWeight": "400", "color": _muted_text(palette),
            "zIndex": 1,
        })

    if img_url:
        elements.append({
            "id": _uid(), "type": "image", "content": img_url,
            "x": 80, "y": 250, "width": 960, "height": 720,
            "zIndex": 2,
        })

    # Build swatches from real palette roles — deduplicated
    _seen: set[str] = set()
    swatch_data: list[tuple[str, str]] = []
    for hex_c, label in [
        (palette["primary"], "Primary"),
        (palette["foreground"], "Foreground"),
        (palette["background"], "Background"),
        (palette.get("secondary", ""), "Secondary"),
    ]:
        if hex_c and hex_c.upper() not in _seen:
            _seen.add(hex_c.upper())
            swatch_data.append((hex_c, label))
    for i, acc in enumerate(palette["accents"][:4]):
        if acc and acc.upper() not in _seen:
            _seen.add(acc.upper())
            swatch_data.append((acc, f"Accent {i + 1}"))

    swatch_x_start = 1100
    swatch_size = 140
    gap = 20
    cols = 2
    for idx, (hex_c, label) in enumerate(swatch_data[:6]):
        col = idx % cols
        row = idx // cols
        x = swatch_x_start + col * (swatch_size + gap + 60)
        y = 250 + row * (swatch_size + 70)

        elements.append({
            "id": _uid(), "type": "shape", "content": hex_c,
            "x": x, "y": y, "width": swatch_size, "height": swatch_size,
            "zIndex": 10 + idx * 2,
        })
        elements.append({
            "id": _uid(), "type": "text", "content": f"{label}\n{hex_c}",
            "x": x, "y": y + swatch_size + 8, "width": swatch_size + 40, "height": 45,
            "fontSize": 14, "fontWeight": "500", "color": _muted_text(palette),
            "zIndex": 11 + idx * 2,
        })

    if logo_url:
        elements.append({
            "id": _uid(), "type": "image", "content": logo_url,
            "x": 1100, "y": 820, "width": 300, "height": 140,
            "zIndex": 30,
        })

    return elements, bg


def _layout_cta(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """CTA / close slide — primary bg, big title, logo, bleeding decoration."""
    bg = palette["primary"]
    elements: list[dict] = []

    # Full-color shape background (ensures color even if bg not rendered)
    elements.append({
        "id": _uid(), "type": "shape", "content": palette["primary"],
        "x": 0, "y": 0, "width": 1920, "height": 1080,
        "zIndex": 0,
    })

    # Decorative circle bleeding off top-right corner
    accent = _rotate_accent(palette, 0)
    elements.append({
        "id": _uid(), "type": "shape", "content": accent,
        "x": 1500, "y": -200, "width": 600, "height": 600,
        "opacity": 0.25, "zIndex": 1,
    })

    # Second smaller circle bleeding off bottom-left
    elements.append({
        "id": _uid(), "type": "shape", "content": accent,
        "x": -150, "y": 800, "width": 400, "height": 400,
        "opacity": 0.15, "zIndex": 1,
    })

    # Title — moved up to y=200, reduced fontSize to 84, generous height
    elements.append({
        "id": _uid(), "type": "text", "content": slide.get("title", ""),
        "x": 80, "y": 200, "width": 1760, "height": 300,
        "fontSize": 84, "fontWeight": "900", "color": "#ffffff",
        "zIndex": 30,
    })

    # Subtitle — well below title at y=560, safe gap of 60px minimum
    subtitle = slide.get("subtitle", "")
    if subtitle:
        elements.append({
            "id": _uid(), "type": "text", "content": subtitle,
            "x": 80, "y": 560, "width": 1760, "height": 80,
            "fontSize": 28, "fontWeight": "400", "color": "rgba(255,255,255,0.7)",
            "zIndex": 31,
        })

    if logo_url:
        elements.append({
            "id": _uid(), "type": "image", "content": logo_url,
            "x": 760, "y": 700, "width": 400, "height": 300,
            "zIndex": 40,
        })

    return elements, bg


# ── Layout dispatcher ──────────────────────────────────────

_LAYOUT_DISPATCH = {
    "cover": _layout_cover,
    "split_50_50": _layout_split_50_50,
    "split_with_bullets": _layout_split_with_bullets,
    "three_cards": _layout_three_cards,
    "big_quote": _layout_big_quote,
    "color_palette": _layout_color_palette,
    "cta": _layout_cta,
    # Aliases from AI layout hints
    "hero": _layout_cover,
    "split-left": _layout_split_50_50,
    "split-right": _layout_split_50_50,
    "three-columns": _layout_three_cards,
    "grid-2x2": _layout_split_with_bullets,
    "full-bg": _layout_cta,
    "art": _layout_color_palette,
}

# Default template per AI slide type
_TYPE_TO_LAYOUT = {
    "cover": "cover",
    "problem": "split_50_50",
    "value_prop": "three_cards",
    "solution": "three_cards",
    "differentiators": "three_cards",
    "manifesto": "big_quote",
    "target_persona": "split_with_bullets",
    "competitive_landscape": "split_with_bullets",
    "market_opportunity": "split_with_bullets",
    "brand_voice": "split_with_bullets",
    "messaging_architecture": "split_with_bullets",
    "content_pillars": "three_cards",
    "channel_strategy": "split_with_bullets",
    "kpis_objectives": "three_cards",
    "roadmap": "split_with_bullets",
    "team_credits": "split_with_bullets",
    "brand_visuals": "color_palette",
    "art_direction": "color_palette",
    "art": "color_palette",
    "product_showcase": "split_50_50",
    "strategy": "split_with_bullets",
    "cta": "cta",
    "cta_final": "cta",
    "content": "split_with_bullets",
}


# ── Public API ─────────────────────────────────────────────

def build_presentation(
    brand: dict,
    slide_content: list[dict],
    image_map: dict[int, str],
    art_direction: dict | None = None,
) -> list[dict]:
    """Build the final slide-deck JSON from AI content + real images.

    Uses structured templates and full palette rotation.
    When *art_direction* contains a ``mood_kit`` key, the matching mood-kit
    layout set is used instead of the default templates.
    """
    from app.services.mood_kits import MOOD_REGISTRY
    from app.services.mockup_generator import (
        build_phone_mockup,
        build_multi_phone_mockup,
        build_physical_product_hero,
        build_product_grid,
        build_product_showcase_no_screenshots,
        detect_showcase_type,
    )

    raw_colors = brand.get("colors", {})
    palette = _build_palette(raw_colors)
    logo_url = brand.get("logo_url")
    screenshots = brand.get("screenshots", [])
    product_images = brand.get("product_images", [])
    # Merge both lists (screenshots = legacy/app, product_images = new generic)
    all_product_media = product_images or screenshots

    # Resolve mood-kit layout overrides
    mood_name = (art_direction or {}).get("mood_kit", "").upper()
    mood_layouts = MOOD_REGISTRY.get(mood_name)  # dict[str, callable] | None
    showcase_type = detect_showcase_type(brand)

    slides: list[dict] = []

    for i, sc in enumerate(slide_content):
        num = sc.get("slide_number", i + 1)
        slide_type = sc.get("type", "content")
        ai_layout = sc.get("layout", "")
        img_url = image_map.get(num, "")

        # Special: product_showcase → dispatch by product type
        if slide_type == "product_showcase":
            if showcase_type == "digital_product":
                # Phone mockup (existing behaviour)
                screenshot = all_product_media[0] if all_product_media else None
                if len(all_product_media) >= 2:
                    elements, bg_color = build_multi_phone_mockup(
                        sc, all_product_media[:3], palette, logo_url, mood_name or "BOLD",
                    )
                elif screenshot:
                    elements, bg_color = build_phone_mockup(
                        sc, screenshot, palette, logo_url, mood_name or "BOLD",
                    )
                else:
                    # No screenshots at all → richer concept visual
                    elements, bg_color = build_product_showcase_no_screenshots(
                        sc, palette, logo_url, mood_name or "BOLD",
                    )
            elif len(all_product_media) >= 2:
                # Multiple images → grid
                elements, bg_color = build_product_grid(
                    sc, all_product_media[:4], palette, logo_url, mood_name or "EDITORIAL",
                )
            else:
                # Physical product / service / generic → hero layout
                first_img = all_product_media[0] if all_product_media else None
                elements, bg_color = build_physical_product_hero(
                    sc, first_img, palette, logo_url, mood_name or "EDITORIAL",
                )
            layout_key = "product_showcase"
        else:
            # Pick layout: mood kit first, then type-based template, then AI hint
            layout_fn = None
            layout_key = _TYPE_TO_LAYOUT.get(slide_type, ai_layout)
            if mood_layouts:
                layout_fn = mood_layouts.get(slide_type)

            if layout_fn is None:
                layout_fn = _LAYOUT_DISPATCH.get(layout_key, _layout_split_with_bullets)

            elements, bg_color = layout_fn(sc, img_url, palette, logo_url)

        slides.append({
            "id": _slide_id(num),
            "type": slide_type,
            "backgroundColor": bg_color,
            "transition": "fade",
            "image": img_url if layout_key == "cover" else "",
            "elements": elements,
        })

    logger.info("presentation_built", slides=len(slides), brand=brand.get("name"))
    return slides
