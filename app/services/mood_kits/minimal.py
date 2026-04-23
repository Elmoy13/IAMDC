"""MINIMAL mood kit — corporate, clean, professional, restrained.

Strict grid, single accent color, monochrome photography,
precise typography, high whitespace ratio.
"""
from app.services.mood_kits._helpers import uid, text_on_bg, muted, rotate_accent


def minimal_cover(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Small accent stripe top
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": 0, "y": 0, "width": 1920, "height": 6, "zIndex": 5})

    # Title — centered, medium weight
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 200, "y": 340, "width": 1520, "height": 200,
                "fontSize": 72, "fontWeight": "600", "color": fg,
                "textAlign": "center", "zIndex": 60})

    # Thin rule
    els.append({"id": uid(), "type": "shape", "content": fg,
                "x": 860, "y": 570, "width": 200, "height": 2, "opacity": 0.25, "zIndex": 5})

    # Subtitle
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 400, "y": 610, "width": 1120, "height": 60,
                     "fontSize": 22, "fontWeight": "400", "color": muted(palette),
                     "textAlign": "center", "zIndex": 61})

    # Logo small bottom-center
    if logo_url:
        els.append({"id": uid(), "type": "image", "content": logo_url,
                     "x": 810, "y": 860, "width": 300, "height": 140, "zIndex": 90})

    return els, bg


def minimal_statement(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Clean statement — left-aligned, maximum whitespace."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Accent bar left edge
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": 80, "y": 200, "width": 4, "height": 400, "zIndex": 5})

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 120, "y": 260, "width": 1400, "height": 200,
                "fontSize": 48, "fontWeight": "600", "color": fg, "zIndex": 60})

    # Subtitle / source
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 120, "y": 500, "width": 1200, "height": 60,
                     "fontSize": 20, "fontWeight": "400", "color": muted(palette), "zIndex": 61})

    return els, bg


def minimal_value_prop(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Strict 3-column grid with only primary accent for numbers."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 60, "width": 1760, "height": 80,
                "fontSize": 44, "fontWeight": "600", "color": fg, "zIndex": 60})

    # Rule below title
    els.append({"id": uid(), "type": "shape", "content": fg,
                "x": 80, "y": 160, "width": 1760, "height": 1, "opacity": 0.1, "zIndex": 2})

    items = slide.get("body_items", [])
    col_w = 540
    gap = 50
    total = min(len(items), 3) * col_w + (min(len(items), 3) - 1) * gap
    start_x = (1920 - total) // 2

    for i in range(min(len(items), 3)):
        x = start_x + i * (col_w + gap)

        # Accent number — only primary, no alternation
        els.append({"id": uid(), "type": "text", "content": f"0{i + 1}",
                     "x": x, "y": 220, "width": 80, "height": 50,
                     "fontSize": 18, "fontWeight": "700", "color": palette["primary"], "zIndex": 30})

        # Thin top border per card
        els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                     "x": x, "y": 210, "width": col_w, "height": 2, "zIndex": 3})

        # Body
        els.append({"id": uid(), "type": "text", "content": items[i],
                     "x": x, "y": 290, "width": col_w, "height": 500,
                     "fontSize": 22, "fontWeight": "400", "color": fg, "zIndex": 31 + i})

    return els, bg


def minimal_art(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Art direction — two-tone with small swatches in a row."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", "Art Direction"),
                "x": 80, "y": 60, "width": 800, "height": 70,
                "fontSize": 40, "fontWeight": "600", "color": fg, "zIndex": 60})

    # Image
    if img_url:
        els.append({"id": uid(), "type": "image", "content": img_url,
                     "x": 80, "y": 180, "width": 1760, "height": 560, "zIndex": 3})

    # Swatches row — small, aligned bottom
    swatch_colors = [
        palette["primary"],
        palette.get("accent", palette["primary"]),
    ] + palette.get("accents", [])[:3]

    x = 80
    for idx, color in enumerate(swatch_colors[:5]):
        els.append({"id": uid(), "type": "shape", "content": color,
                     "x": x, "y": 800, "width": 120, "height": 80, "zIndex": 10 + idx})
        els.append({"id": uid(), "type": "text", "content": color,
                     "x": x, "y": 890, "width": 120, "height": 25,
                     "fontSize": 12, "fontWeight": "500", "color": muted(palette),
                     "textAlign": "center", "zIndex": 11 + idx})
        x += 160

    return els, bg


def minimal_strategy(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Strict numbered list — pure grid, no decorations."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 80, "width": 1400, "height": 80,
                "fontSize": 44, "fontWeight": "600", "color": fg, "zIndex": 60})

    # Rule
    els.append({"id": uid(), "type": "shape", "content": fg,
                "x": 80, "y": 175, "width": 1760, "height": 1, "opacity": 0.1, "zIndex": 2})

    items = slide.get("body_items", [])
    y = 230
    for i, item in enumerate(items[:5]):
        # Number
        els.append({"id": uid(), "type": "text", "content": f"{i + 1}",
                     "x": 80, "y": y, "width": 60, "height": 45,
                     "fontSize": 18, "fontWeight": "700", "color": palette["primary"], "zIndex": 30 + i * 2})
        # Text
        els.append({"id": uid(), "type": "text", "content": item,
                     "x": 160, "y": y, "width": 1500, "height": 80,
                     "fontSize": 22, "fontWeight": "400", "color": fg, "zIndex": 31 + i * 2})
        y += 130

    return els, bg


def minimal_cta(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Simple CTA — centered title, accent bar, nothing else."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Accent stripe top
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": 0, "y": 0, "width": 1920, "height": 6, "zIndex": 5})

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 200, "y": 340, "width": 1520, "height": 200,
                "fontSize": 56, "fontWeight": "600", "color": fg,
                "textAlign": "center", "zIndex": 60})

    # Subtitle
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 400, "y": 570, "width": 1120, "height": 60,
                     "fontSize": 20, "fontWeight": "400", "color": muted(palette),
                     "textAlign": "center", "zIndex": 61})

    # Logo centered
    if logo_url:
        els.append({"id": uid(), "type": "image", "content": logo_url,
                     "x": 810, "y": 740, "width": 300, "height": 180, "zIndex": 90})

    return els, bg


# ── Registry ───────────────────────────────────────────────

MINIMAL_LAYOUTS: dict[str, callable] = {
    # Essential
    "cover": minimal_cover,
    "cta": minimal_cta,
    "cta_final": minimal_cta,
    # Core strategic
    "manifesto": minimal_statement,
    "problem": minimal_statement,
    "solution": minimal_value_prop,
    "differentiators": minimal_value_prop,
    "value_prop": minimal_value_prop,
    # Deep strategic
    "target_persona": minimal_strategy,
    "competitive_landscape": minimal_strategy,
    "market_opportunity": minimal_strategy,
    "brand_voice": minimal_strategy,
    "messaging_architecture": minimal_strategy,
    "content_pillars": minimal_value_prop,
    "channel_strategy": minimal_strategy,
    "kpis_objectives": minimal_value_prop,
    "roadmap": minimal_strategy,
    "team_credits": minimal_strategy,
    # Visual
    "brand_visuals": minimal_art,
    "art_direction": minimal_art,
    "art": minimal_art,
    "product_showcase": minimal_statement,
    # Strategy alias
    "strategy": minimal_strategy,
    "content": minimal_statement,
}
