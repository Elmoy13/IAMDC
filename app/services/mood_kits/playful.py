"""PLAYFUL mood kit — fun, colorful, genZ, geometric, vibrant.

Rounded shapes, pastel accent blobs, emoji-style badges,
diagonals, stickers, energetic asymmetry.
"""
from app.services.mood_kits._helpers import uid, text_on_bg, muted, rotate_accent


def playful_cover(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Pastel accent blob top-left
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": -100, "y": -100, "width": 700, "height": 700, "opacity": 0.25, "zIndex": 1})

    # Secondary blob bottom-right
    accent = palette.get("accent", palette["primary"])
    els.append({"id": uid(), "type": "shape", "content": accent,
                "x": 1400, "y": 600, "width": 700, "height": 700, "opacity": 0.2, "zIndex": 1})

    # Hero image — centered circle-ish crop (placed as rectangle, frontend can clip)
    if img_url:
        els.append({"id": uid(), "type": "image", "content": img_url,
                     "x": 560, "y": 100, "width": 800, "height": 600, "zIndex": 3})

    # Title — big, playful weight
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 750, "width": 1760, "height": 200,
                "fontSize": 96, "fontWeight": "800", "color": fg,
                "textAlign": "center", "zIndex": 60})

    # Subtitle
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 300, "y": 960, "width": 1320, "height": 60,
                     "fontSize": 24, "fontWeight": "500", "color": muted(palette),
                     "textAlign": "center", "zIndex": 61})

    return els, bg


def playful_problem(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Sticker-style callout cards on a colorful background."""
    bg = palette.get("accent", palette["primary"])
    els: list[dict] = []

    # Light background
    els.append({"id": uid(), "type": "shape", "content": bg,
                "x": 0, "y": 0, "width": 1920, "height": 1080, "opacity": 0.15, "zIndex": 0})

    # Giant rotated emoji/symbol as decoration
    els.append({"id": uid(), "type": "text", "content": "⚡",
                "x": 1500, "y": -40, "width": 400, "height": 400,
                "fontSize": 300, "opacity": 0.12, "zIndex": 1})

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 60, "width": 1400, "height": 120,
                "fontSize": 64, "fontWeight": "800", "color": palette["foreground"], "zIndex": 60})

    items = slide.get("body_items", [])
    y = 260
    for i, item in enumerate(items[:4]):
        accent_c = rotate_accent(palette, i)

        # "Sticker" card background
        els.append({"id": uid(), "type": "shape", "content": palette["background"],
                     "x": 80, "y": y, "width": 1760, "height": 150, "zIndex": 5 + i})
        # Accent left bar
        els.append({"id": uid(), "type": "shape", "content": accent_c,
                     "x": 80, "y": y, "width": 8, "height": 150, "zIndex": 6 + i * 3})
        # Text
        els.append({"id": uid(), "type": "text", "content": item,
                     "x": 120, "y": y + 35, "width": 1680, "height": 80,
                     "fontSize": 26, "fontWeight": "600", "color": palette["foreground"], "zIndex": 30 + i})
        y += 185

    return els, palette["background"]


def playful_value_prop(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Fun grid cards with colored headers and playful shapes."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 60, "width": 1760, "height": 100,
                "fontSize": 64, "fontWeight": "800", "color": fg,
                "textAlign": "center", "zIndex": 60})

    items = slide.get("body_items", [])
    col_w = 540
    gap = 50
    total = min(len(items), 3) * col_w + (min(len(items), 3) - 1) * gap
    start_x = (1920 - total) // 2

    for i in range(min(len(items), 3)):
        x = start_x + i * (col_w + gap)
        accent_c = rotate_accent(palette, i)

        # Card bg
        els.append({"id": uid(), "type": "shape", "content": accent_c,
                     "x": x, "y": 220, "width": col_w, "height": 700, "opacity": 0.12, "zIndex": 2 + i})

        # Card number badge — circle-style
        els.append({"id": uid(), "type": "shape", "content": accent_c,
                     "x": x + col_w // 2 - 40, "y": 260, "width": 80, "height": 80, "zIndex": 10 + i})
        els.append({"id": uid(), "type": "text", "content": f"{i + 1}",
                     "x": x + col_w // 2 - 40, "y": 268, "width": 80, "height": 70,
                     "fontSize": 36, "fontWeight": "900", "color": "#FFFFFF",
                     "textAlign": "center", "zIndex": 11 + i})

        # Card text
        els.append({"id": uid(), "type": "text", "content": items[i],
                     "x": x + 30, "y": 380, "width": col_w - 60, "height": 500,
                     "fontSize": 24, "fontWeight": "500", "color": fg,
                     "textAlign": "center", "zIndex": 30 + i})

    return els, bg


def playful_art(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Art direction with scattered color blobs and a moodboard frame."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", "Art Direction"),
                "x": 80, "y": 60, "width": 900, "height": 80,
                "fontSize": 52, "fontWeight": "800", "color": fg, "zIndex": 60})

    # Moodboard image
    if img_url:
        els.append({"id": uid(), "type": "image", "content": img_url,
                     "x": 80, "y": 200, "width": 860, "height": 740, "zIndex": 3})

    # Fun swatches — scattered circles
    swatch_colors = [
        palette["primary"],
        palette.get("accent", palette["primary"]),
    ] + palette.get("accents", [])[:3]

    positions = [(1060, 220), (1320, 220), (1060, 470), (1320, 470), (1190, 700)]
    size = 200
    for idx, color in enumerate(swatch_colors[:5]):
        x, y = positions[idx]
        els.append({"id": uid(), "type": "shape", "content": color,
                     "x": x, "y": y, "width": size, "height": size, "zIndex": 10 + idx})
        els.append({"id": uid(), "type": "text", "content": color,
                     "x": x, "y": y + size + 8, "width": size, "height": 28,
                     "fontSize": 14, "fontWeight": "700", "color": muted(palette),
                     "textAlign": "center", "zIndex": 11 + idx})

    return els, bg


def playful_strategy(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Zigzag-style steps with alternating accent blocks."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 60, "width": 1400, "height": 110,
                "fontSize": 60, "fontWeight": "800", "color": fg, "zIndex": 60})

    items = slide.get("body_items", [])
    y = 240
    for i, item in enumerate(items[:4]):
        accent_c = rotate_accent(palette, i)
        x_offset = 120 if i % 2 == 0 else 400  # zigzag

        # Accent block
        els.append({"id": uid(), "type": "shape", "content": accent_c,
                     "x": x_offset - 20, "y": y, "width": 1400, "height": 150,
                     "opacity": 0.1, "zIndex": 2 + i})

        # Number badge
        els.append({"id": uid(), "type": "shape", "content": accent_c,
                     "x": x_offset, "y": y + 30, "width": 70, "height": 70, "zIndex": 10 + i})
        els.append({"id": uid(), "type": "text", "content": f"{i + 1}",
                     "x": x_offset, "y": y + 38, "width": 70, "height": 55,
                     "fontSize": 32, "fontWeight": "900", "color": "#FFFFFF",
                     "textAlign": "center", "zIndex": 11 + i})

        # Body text
        els.append({"id": uid(), "type": "text", "content": item,
                     "x": x_offset + 100, "y": y + 40, "width": 1200, "height": 70,
                     "fontSize": 26, "fontWeight": "600", "color": fg, "zIndex": 30 + i})
        y += 190

    return els, bg


def playful_cta(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """High-energy CTA with oversized emoji and stacked shapes."""
    bg = palette["primary"]
    els: list[dict] = []

    # Primary bg
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": 0, "y": 0, "width": 1920, "height": 1080, "zIndex": 0})

    # Decorative shapes
    accent = palette.get("accent", "#FAFAFA")
    els.append({"id": uid(), "type": "shape", "content": accent,
                "x": 100, "y": 100, "width": 300, "height": 300, "opacity": 0.15, "zIndex": 1})
    els.append({"id": uid(), "type": "shape", "content": palette["background"],
                "x": 1500, "y": 700, "width": 500, "height": 500, "opacity": 0.1, "zIndex": 1})

    # Giant emoji
    els.append({"id": uid(), "type": "text", "content": "🚀",
                "x": 800, "y": 40, "width": 320, "height": 280,
                "fontSize": 200, "zIndex": 2})

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 350, "width": 1760, "height": 250,
                "fontSize": 88, "fontWeight": "800", "color": "#FAFAFA",
                "textAlign": "center", "zIndex": 60})

    # Subtitle
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 300, "y": 640, "width": 1320, "height": 80,
                     "fontSize": 26, "fontWeight": "500", "color": "rgba(255,255,255,0.7)",
                     "textAlign": "center", "zIndex": 61})

    # Logo
    if logo_url:
        els.append({"id": uid(), "type": "image", "content": logo_url,
                     "x": 760, "y": 780, "width": 400, "height": 220, "zIndex": 90})

    return els, bg


# ── Registry ───────────────────────────────────────────────

PLAYFUL_LAYOUTS: dict[str, callable] = {
    # Essential
    "cover": playful_cover,
    "cta": playful_cta,
    "cta_final": playful_cta,
    # Core strategic
    "manifesto": playful_cover,
    "problem": playful_problem,
    "solution": playful_value_prop,
    "differentiators": playful_value_prop,
    "value_prop": playful_value_prop,
    # Deep strategic
    "target_persona": playful_strategy,
    "competitive_landscape": playful_strategy,
    "market_opportunity": playful_strategy,
    "brand_voice": playful_strategy,
    "messaging_architecture": playful_strategy,
    "content_pillars": playful_value_prop,
    "channel_strategy": playful_strategy,
    "kpis_objectives": playful_value_prop,
    "roadmap": playful_strategy,
    "team_credits": playful_strategy,
    # Visual
    "brand_visuals": playful_art,
    "art_direction": playful_art,
    "art": playful_art,
    "product_showcase": playful_problem,
    # Strategy alias
    "strategy": playful_strategy,
    "content": playful_problem,
}
