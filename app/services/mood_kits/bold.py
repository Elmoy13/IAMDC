"""BOLD mood kit — irreverente, vibrante, party, gen-z.

Giant typography, saturated color blocks, decorative numbers,
organic shapes, high-energy asymmetric layouts.
"""
from app.services.mood_kits._helpers import uid, text_on_bg, muted, rotate_accent

# ── Layout functions ───────────────────────────────────────
# Signature: (slide, img_url, palette, logo_url) -> (elements, bg)


def bold_cover(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    bg = palette["primary"]
    els: list[dict] = []

    # Full primary background shape
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": 0, "y": 0, "width": 1920, "height": 1080, "zIndex": 0})

    # Hero image with low opacity
    if img_url:
        els.append({"id": uid(), "type": "image", "content": img_url,
                     "x": 0, "y": 0, "width": 1920, "height": 1080,
                     "opacity": 0.35, "zIndex": 1})

    # Decorative blob top-right (accent, bleeds off canvas)
    els.append({"id": uid(), "type": "shape", "content": palette.get("accent", palette["primary"]),
                "x": 1300, "y": -200, "width": 800, "height": 800, "opacity": 0.2, "zIndex": 2})

    # Giant title — bottom-left, oversized
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 500, "width": 1700, "height": 350,
                "fontSize": 140, "fontWeight": "900", "color": "#FAFAFA", "zIndex": 60})

    # Tagline
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 80, "y": 870, "width": 1200, "height": 60,
                     "fontSize": 28, "fontWeight": "400", "color": "rgba(255,255,255,0.7)", "zIndex": 61})

    return els, bg


def bold_problem(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Split layout with emotional image left + bold bullets right on dark bg."""
    bg = palette.get("foreground", "#0F172A")
    els: list[dict] = []

    # Dark background shape
    els.append({"id": uid(), "type": "shape", "content": bg,
                "x": 0, "y": 0, "width": 1920, "height": 1080, "zIndex": 0})

    # Image — left 45%
    if img_url:
        els.append({"id": uid(), "type": "image", "content": img_url,
                     "x": 0, "y": 0, "width": 860, "height": 1080, "zIndex": 1})

    # Decorative number "02" giant behind text
    els.append({"id": uid(), "type": "text", "content": "02",
                "x": 850, "y": 50, "width": 600, "height": 500,
                "fontSize": 400, "fontWeight": "900", "color": palette["primary"], "opacity": 0.1, "zIndex": 2})

    # Title — right side
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 940, "y": 100, "width": 900, "height": 160,
                "fontSize": 64, "fontWeight": "900", "color": "#FAFAFA", "zIndex": 60})

    # Bullet items with accent markers
    items = slide.get("body_items", [])
    y = 310
    for i, item in enumerate(items[:5]):
        accent = rotate_accent(palette, i)
        # Accent bar
        els.append({"id": uid(), "type": "shape", "content": accent,
                     "x": 940, "y": y + 6, "width": 6, "height": 60, "zIndex": 30 + i * 2})
        els.append({"id": uid(), "type": "text", "content": item,
                     "x": 970, "y": y, "width": 870, "height": 75,
                     "fontSize": 24, "fontWeight": "500", "color": "rgba(255,255,255,0.85)", "zIndex": 31 + i * 2})
        y += 120

    return els, bg


def bold_value_prop(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """3 numbered columns on primary bg — giant numbers as focal points."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 60, "width": 1760, "height": 120,
                "fontSize": 72, "fontWeight": "900", "color": fg, "zIndex": 60})

    # Subtitle
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 80, "y": 185, "width": 1760, "height": 50,
                     "fontSize": 24, "fontWeight": "400", "color": muted(palette), "zIndex": 61})

    items = slide.get("body_items", [])
    col_w = 550
    gap = 45
    start_x = 80

    for i in range(min(len(items), 3)):
        x = start_x + i * (col_w + gap)
        accent = rotate_accent(palette, i)

        # Giant number behind
        els.append({"id": uid(), "type": "text", "content": f"0{i + 1}",
                     "x": x, "y": 240, "width": 400, "height": 400,
                     "fontSize": 280, "fontWeight": "900", "color": accent, "opacity": 0.12, "zIndex": 1})

        # Vertical divider between columns (except last)
        if i < min(len(items), 3) - 1:
            div_x = x + col_w + gap // 2
            els.append({"id": uid(), "type": "shape", "content": palette.get("foreground", "#161B26"),
                         "x": div_x, "y": 280, "width": 2, "height": 600, "opacity": 0.15, "zIndex": 2})

        # Card body
        els.append({"id": uid(), "type": "text", "content": items[i],
                     "x": x + 20, "y": 520, "width": col_w - 40, "height": 400,
                     "fontSize": 26, "fontWeight": "500", "color": fg, "zIndex": 30 + i})

    return els, bg


def bold_art(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Art direction slide: big swatches + moodboard image + bold typography."""
    bg = palette["foreground"]
    els: list[dict] = []

    # Dark BG
    els.append({"id": uid(), "type": "shape", "content": bg,
                "x": 0, "y": 0, "width": 1920, "height": 1080, "zIndex": 0})

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", "Dirección de Arte"),
                "x": 80, "y": 60, "width": 900, "height": 90,
                "fontSize": 64, "fontWeight": "900", "color": "#FAFAFA", "zIndex": 60})

    # Moodboard image
    if img_url:
        els.append({"id": uid(), "type": "image", "content": img_url,
                     "x": 80, "y": 200, "width": 900, "height": 700, "zIndex": 3})

    # Large swatches — right side, oversized circles
    swatch_colors = [
        palette["primary"],
        palette.get("accent", palette["primary"]),
    ] + palette.get("accents", [])[:3]

    swatch_size = 200
    x_start = 1080
    for idx, color in enumerate(swatch_colors[:4]):
        col = idx % 2
        row = idx // 2
        x = x_start + col * (swatch_size + 40)
        y = 200 + row * (swatch_size + 80)
        els.append({"id": uid(), "type": "shape", "content": color,
                     "x": x, "y": y, "width": swatch_size, "height": swatch_size, "zIndex": 10 + idx})
        els.append({"id": uid(), "type": "text", "content": color,
                     "x": x, "y": y + swatch_size + 10, "width": swatch_size, "height": 30,
                     "fontSize": 18, "fontWeight": "700", "color": "rgba(255,255,255,0.6)", "zIndex": 11 + idx})

    return els, bg


def bold_strategy(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """Strategy slide: large numbered items on alternating colored bars."""
    bg = palette["background"]
    fg = palette["foreground"]
    els: list[dict] = []

    # Decorative blob bottom-left
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": -150, "y": 700, "width": 600, "height": 600, "opacity": 0.1, "zIndex": 1})

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 60, "width": 1400, "height": 120,
                "fontSize": 72, "fontWeight": "900", "color": fg, "zIndex": 60})

    items = slide.get("body_items", [])
    y = 240
    for i, item in enumerate(items[:4]):
        accent = rotate_accent(palette, i)
        # Colored bar
        els.append({"id": uid(), "type": "shape", "content": accent,
                     "x": 80, "y": y, "width": 1760, "height": 160, "opacity": 0.12, "zIndex": 2 + i})
        # Number
        els.append({"id": uid(), "type": "text", "content": f"0{i + 1}",
                     "x": 100, "y": y + 15, "width": 160, "height": 130,
                     "fontSize": 100, "fontWeight": "900", "color": accent, "opacity": 0.5, "zIndex": 30 + i * 2})
        # Text
        els.append({"id": uid(), "type": "text", "content": item,
                     "x": 280, "y": y + 40, "width": 1500, "height": 80,
                     "fontSize": 28, "fontWeight": "600", "color": fg, "zIndex": 31 + i * 2})
        y += 195

    # Image right side if available
    if img_url:
        els.append({"id": uid(), "type": "image", "content": img_url,
                     "x": 1300, "y": 200, "width": 560, "height": 800, "opacity": 0.6, "zIndex": 5})

    return els, bg


def bold_cta(slide: dict, img_url: str, palette: dict, logo_url: str | None) -> tuple[list[dict], str]:
    """CTA slide: saturated bg + giant title + glow ring behind logo."""
    bg = palette["primary"]
    els: list[dict] = []

    # Full primary bg
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": 0, "y": 0, "width": 1920, "height": 1080, "zIndex": 0})

    # Decorative accent circle glow — center
    accent = palette.get("accent", "#FAFAFA")
    els.append({"id": uid(), "type": "shape", "content": accent,
                "x": 660, "y": 240, "width": 600, "height": 600, "opacity": 0.08, "zIndex": 1})

    # Giant title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 180, "width": 1760, "height": 350,
                "fontSize": 100, "fontWeight": "900", "color": "#FAFAFA", "zIndex": 60})

    # Subtitle
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 80, "y": 580, "width": 1760, "height": 80,
                     "fontSize": 28, "fontWeight": "400", "color": "rgba(255,255,255,0.65)", "zIndex": 61})

    # Logo large centered near bottom
    if logo_url:
        els.append({"id": uid(), "type": "image", "content": logo_url,
                     "x": 760, "y": 720, "width": 400, "height": 280, "zIndex": 90})

    return els, bg


# ── Registry ───────────────────────────────────────────────

BOLD_LAYOUTS: dict[str, callable] = {
    # Essential
    "cover": bold_cover,
    "cta": bold_cta,
    "cta_final": bold_cta,
    # Core strategic
    "manifesto": bold_cover,           # reuse cover (sparse, statement)
    "problem": bold_problem,
    "solution": bold_value_prop,
    "differentiators": bold_value_prop,
    "value_prop": bold_value_prop,
    # Deep strategic
    "target_persona": bold_strategy,
    "competitive_landscape": bold_strategy,
    "market_opportunity": bold_strategy,
    "brand_voice": bold_strategy,
    "messaging_architecture": bold_strategy,
    "content_pillars": bold_value_prop,
    "channel_strategy": bold_strategy,
    "kpis_objectives": bold_value_prop,
    "roadmap": bold_strategy,
    "team_credits": bold_strategy,
    # Visual
    "brand_visuals": bold_art,
    "art_direction": bold_art,
    "art": bold_art,
    "product_showcase": bold_problem,   # split layout (image + text)
    # Strategy alias
    "strategy": bold_strategy,
    "content": bold_problem,
}
