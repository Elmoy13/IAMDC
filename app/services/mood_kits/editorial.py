"""EDITORIAL mood kit — premium, high-fashion, magazine, luxury.

Generous negative space, serif-feel headings, thin separators,
muted photo treatments, understated elegance.
"""
from app.services.mood_kits._helpers import uid, text_on_bg, muted, rotate_accent


def editorial_cover(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Hero image — massive, centered with breathing room
    if img_url:
        els.append({"id": uid(), "type": "image", "content": img_url,
                     "x": 960, "y": 0, "width": 960, "height": 1080, "zIndex": 1})

    # Thin vertical accent line
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": 900, "y": 120, "width": 3, "height": 840, "zIndex": 5})

    # Title — left half, refined size
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 260, "width": 780, "height": 340,
                "fontSize": 80, "fontWeight": "300", "color": fg, "zIndex": 60})

    # Subtitle — small caps vibe
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub.upper(),
                     "x": 80, "y": 640, "width": 780, "height": 60,
                     "fontSize": 18, "fontWeight": "500", "letterSpacing": 4,
                     "color": muted(palette), "zIndex": 61})

    return els, bg


def editorial_statement(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Full-bleed quiet statement — single large sentence on generous space."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Optional image as background wash
    if img_url:
        els.append({"id": uid(), "type": "image", "content": img_url,
                     "x": 0, "y": 0, "width": 1920, "height": 1080,
                     "opacity": 0.15, "zIndex": 1})

    # Horizontal rule — thin, centered
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": 860, "y": 280, "width": 200, "height": 2, "zIndex": 5})

    # Big quote-style title / problem statement
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 200, "y": 340, "width": 1520, "height": 260,
                "fontSize": 56, "fontWeight": "300", "color": fg,
                "textAlign": "center", "zIndex": 60})

    # Supporting copy — small, centered beneath
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 400, "y": 650, "width": 1120, "height": 80,
                     "fontSize": 22, "fontWeight": "400", "color": muted(palette),
                     "textAlign": "center", "zIndex": 61})

    return els, bg


def editorial_value_prop(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Elegant 3-column with minimal dividers."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Title — centered, light weight
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 60, "width": 1760, "height": 100,
                "fontSize": 56, "fontWeight": "300", "color": fg,
                "textAlign": "center", "zIndex": 60})

    # Thin horizontal rule below title
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": 860, "y": 180, "width": 200, "height": 2, "zIndex": 5})

    items = slide.get("body_items", [])
    col_w = 520
    gap = 60
    total = min(len(items), 3) * col_w + (min(len(items), 3) - 1) * gap
    start_x = (1920 - total) // 2

    for i in range(min(len(items), 3)):
        x = start_x + i * (col_w + gap)
        accent = rotate_accent(palette, i)

        # Small accent number
        els.append({"id": uid(), "type": "text", "content": f"0{i + 1}",
                     "x": x, "y": 250, "width": 60, "height": 40,
                     "fontSize": 16, "fontWeight": "700", "color": accent, "zIndex": 30})

        # Thin divider between columns
        if i < min(len(items), 3) - 1:
            div_x = x + col_w + gap // 2
            els.append({"id": uid(), "type": "shape", "content": fg,
                         "x": div_x, "y": 260, "width": 1, "height": 500, "opacity": 0.12, "zIndex": 2})

        # Body text
        els.append({"id": uid(), "type": "text", "content": items[i],
                     "x": x, "y": 310, "width": col_w, "height": 500,
                     "fontSize": 22, "fontWeight": "400", "color": fg, "zIndex": 31 + i})

    return els, bg


def editorial_art(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Art direction — clean swatches + restrained layout."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", "Art Direction"),
                "x": 80, "y": 60, "width": 800, "height": 80,
                "fontSize": 48, "fontWeight": "300", "color": fg, "zIndex": 60})

    # Image — left
    if img_url:
        els.append({"id": uid(), "type": "image", "content": img_url,
                     "x": 80, "y": 200, "width": 860, "height": 740, "zIndex": 3})

    # Swatches — right side, elegant rectangles
    swatch_colors = [
        palette["primary"],
        palette.get("accent", palette["primary"]),
    ] + palette.get("accents", [])[:3]

    y = 200
    for idx, color in enumerate(swatch_colors[:5]):
        els.append({"id": uid(), "type": "shape", "content": color,
                     "x": 1040, "y": y, "width": 300, "height": 100, "zIndex": 10 + idx})
        els.append({"id": uid(), "type": "text", "content": color,
                     "x": 1370, "y": y + 35, "width": 200, "height": 30,
                     "fontSize": 16, "fontWeight": "400", "color": muted(palette), "zIndex": 11 + idx})
        y += 140

    return els, bg


def editorial_strategy(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Clean numbered list with generous spacing."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Title — left-aligned, thin
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 80, "width": 1400, "height": 100,
                "fontSize": 56, "fontWeight": "300", "color": fg, "zIndex": 60})

    items = slide.get("body_items", [])
    y = 260
    for i, item in enumerate(items[:5]):
        # Number
        els.append({"id": uid(), "type": "text", "content": f"0{i + 1}.",
                     "x": 80, "y": y, "width": 100, "height": 50,
                     "fontSize": 20, "fontWeight": "700", "color": palette["primary"], "zIndex": 30 + i * 2})
        # Body
        els.append({"id": uid(), "type": "text", "content": item,
                     "x": 190, "y": y, "width": 1400, "height": 90,
                     "fontSize": 24, "fontWeight": "400", "color": fg, "zIndex": 31 + i * 2})
        # Light separator
        if i < len(items) - 1:
            els.append({"id": uid(), "type": "shape", "content": fg,
                         "x": 80, "y": y + 100, "width": 1520, "height": 1, "opacity": 0.08, "zIndex": 2})
        y += 140

    return els, bg


def editorial_cta(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Restrained CTA — centered, minimal, elegant."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Optional faded image
    if img_url:
        els.append({"id": uid(), "type": "image", "content": img_url,
                     "x": 0, "y": 0, "width": 1920, "height": 1080,
                     "opacity": 0.1, "zIndex": 1})

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 200, "y": 300, "width": 1520, "height": 200,
                "fontSize": 72, "fontWeight": "300", "color": fg,
                "textAlign": "center", "zIndex": 60})

    # Thin rule below
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": 860, "y": 540, "width": 200, "height": 2, "zIndex": 5})

    # Subtitle
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 400, "y": 580, "width": 1120, "height": 80,
                     "fontSize": 22, "fontWeight": "400", "color": muted(palette),
                     "textAlign": "center", "zIndex": 61})

    # Logo small centered
    if logo_url:
        els.append({"id": uid(), "type": "image", "content": logo_url,
                     "x": 810, "y": 740, "width": 300, "height": 200, "zIndex": 90})

    return els, bg


# ── Registry ───────────────────────────────────────────────

EDITORIAL_LAYOUTS: dict[str, callable] = {
    # Essential
    "cover": editorial_cover,
    "cta": editorial_cta,
    "cta_final": editorial_cta,
    # Core strategic
    "manifesto": editorial_statement,
    "problem": editorial_statement,
    "solution": editorial_value_prop,
    "differentiators": editorial_value_prop,
    "value_prop": editorial_value_prop,
    # Deep strategic
    "target_persona": editorial_strategy,
    "competitive_landscape": editorial_strategy,
    "market_opportunity": editorial_strategy,
    "brand_voice": editorial_strategy,
    "messaging_architecture": editorial_strategy,
    "content_pillars": editorial_value_prop,
    "channel_strategy": editorial_strategy,
    "kpis_objectives": editorial_value_prop,
    "roadmap": editorial_strategy,
    "team_credits": editorial_strategy,
    # Visual
    "brand_visuals": editorial_art,
    "art_direction": editorial_art,
    "art": editorial_art,
    "product_showcase": editorial_cover,
    # Strategy alias
    "strategy": editorial_strategy,
    "content": editorial_statement,
}
