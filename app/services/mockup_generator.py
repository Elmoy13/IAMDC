"""Mockup generator — phone frame templates for digital products.

Produces slide elements that render a phone mockup with an app screenshot
inside, plus supporting copy and decorative elements.
"""
from app.services.mood_kits._helpers import uid, text_on_bg, muted, rotate_accent


_PHONE_FRAME_W = 380
_PHONE_FRAME_H = 780
_PHONE_BORDER = 20  # inner padding for screenshot


def build_phone_mockup(
    slide: dict,
    screenshot_url: str | None,
    palette: dict,
    logo_url: str | None,
    mood_kit: str = "BOLD",
) -> tuple[list[dict], str]:
    """Build a product_showcase slide with a centred phone mockup.

    Args:
        slide: AI-generated slide content (title, subtitle, body_items).
        screenshot_url: URL of the app screenshot (from user uploads).
        palette: Brand palette dict.
        logo_url: Optional brand logo URL.
        mood_kit: Active mood kit name (affects colour choices).

    Returns:
        (elements, backgroundColor)
    """
    is_dark = mood_kit in ("BOLD", "EDITORIAL")
    bg = palette.get("foreground", "#0F172A") if is_dark else palette["background"]
    text_color = "#FAFAFA" if is_dark else palette["foreground"]
    muted_color = "rgba(255,255,255,0.6)" if is_dark else muted(palette)

    els: list[dict] = []

    # Background shape
    els.append({"id": uid(), "type": "shape", "content": bg,
                "x": 0, "y": 0, "width": 1920, "height": 1080, "zIndex": 0})

    # Decorative blob behind phone
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": 600, "y": 100, "width": 720, "height": 720,
                "opacity": 0.15, "zIndex": 1})

    # Phone frame (dark rectangle)
    phone_x = 760
    phone_y = 130
    els.append({"id": uid(), "type": "shape", "content": "#0a0a0a",
                "x": phone_x, "y": phone_y,
                "width": _PHONE_FRAME_W + 2 * _PHONE_BORDER,
                "height": _PHONE_FRAME_H + 2 * _PHONE_BORDER,
                "borderRadius": 50, "zIndex": 10})

    # Screenshot inside frame (or placeholder)
    if screenshot_url:
        els.append({"id": uid(), "type": "image", "content": screenshot_url,
                     "x": phone_x + _PHONE_BORDER,
                     "y": phone_y + _PHONE_BORDER,
                     "width": _PHONE_FRAME_W,
                     "height": _PHONE_FRAME_H,
                     "borderRadius": 36, "zIndex": 11})
    else:
        # Rich placeholder — brand-coloured screen with logo + accent bars
        els.append({"id": uid(), "type": "shape",
                     "content": palette["primary"],
                     "x": phone_x + _PHONE_BORDER,
                     "y": phone_y + _PHONE_BORDER,
                     "width": _PHONE_FRAME_W,
                     "height": _PHONE_FRAME_H,
                     "borderRadius": 36, "opacity": 0.6, "zIndex": 11})
        # Logo centred inside placeholder
        if logo_url:
            els.append({"id": uid(), "type": "image", "content": logo_url,
                         "x": phone_x + _PHONE_BORDER + 90,
                         "y": phone_y + _PHONE_BORDER + 200,
                         "width": 200, "height": 200, "zIndex": 12})
        # Accent accent bars to simulate UI elements inside the phone
        accent_c = palette.get("accent", palette["primary"])
        for bar_i in range(3):
            bar_y = phone_y + _PHONE_BORDER + 460 + bar_i * 60
            els.append({"id": uid(), "type": "shape", "content": "#ffffff",
                         "x": phone_x + _PHONE_BORDER + 40,
                         "y": bar_y,
                         "width": _PHONE_FRAME_W - 80,
                         "height": 36,
                         "opacity": 0.25, "borderRadius": 8, "zIndex": 12})
        # Small "concept" label below logo in the phone
        els.append({"id": uid(), "type": "text",
                     "content": slide.get("title", "")[:30] or "App Preview",
                     "x": phone_x + _PHONE_BORDER + 40,
                     "y": phone_y + _PHONE_BORDER + 420,
                     "width": _PHONE_FRAME_W - 80, "height": 40,
                     "fontSize": 16, "fontWeight": "600",
                     "color": "#ffffff", "textAlign": "center", "zIndex": 13})

    # Title — left of mockup
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 200, "width": 620, "height": 240,
                "fontSize": 64, "fontWeight": "900", "color": text_color, "zIndex": 30})

    # Subtitle — below title
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 80, "y": 460, "width": 620, "height": 80,
                     "fontSize": 24, "fontWeight": "400", "color": muted_color, "zIndex": 31})

    # Feature bullets (up to 3) — fill space on the left
    body = slide.get("body_items", [])
    for i, item in enumerate(body[:3]):
        y = 580 + i * 80
        els.append({"id": uid(), "type": "shape", "content": palette.get("accent", palette["primary"]),
                     "x": 80, "y": y + 8, "width": 10, "height": 10,
                     "zIndex": 32 + i * 2})
        els.append({"id": uid(), "type": "text", "content": item,
                     "x": 106, "y": y, "width": 590, "height": 60,
                     "fontSize": 20, "fontWeight": "400", "color": muted_color,
                     "zIndex": 33 + i * 2})

    return els, bg


def build_multi_phone_mockup(
    slide: dict,
    screenshot_urls: list[str],
    palette: dict,
    logo_url: str | None,
    mood_kit: str = "BOLD",
) -> tuple[list[dict], str]:
    """Variant: 2-3 phone mockups side by side for multi-screen showcase."""
    is_dark = mood_kit in ("BOLD", "EDITORIAL")
    bg = palette.get("foreground", "#0F172A") if is_dark else palette["background"]
    text_color = "#FAFAFA" if is_dark else palette["foreground"]
    muted_color = "rgba(255,255,255,0.6)" if is_dark else muted(palette)

    els: list[dict] = []

    # Background
    els.append({"id": uid(), "type": "shape", "content": bg,
                "x": 0, "y": 0, "width": 1920, "height": 1080, "zIndex": 0})

    # Title top
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 40, "width": 1760, "height": 100,
                "fontSize": 56, "fontWeight": "900", "color": text_color,
                "textAlign": "center", "zIndex": 60})

    # Place up to 3 phones
    count = min(len(screenshot_urls), 3) or 1
    phone_scale = 0.7 if count >= 3 else 0.85
    fw = int((_PHONE_FRAME_W + 2 * _PHONE_BORDER) * phone_scale)
    fh = int((_PHONE_FRAME_H + 2 * _PHONE_BORDER) * phone_scale)
    sw = int(_PHONE_FRAME_W * phone_scale)
    sh = int(_PHONE_FRAME_H * phone_scale)
    border_s = int(_PHONE_BORDER * phone_scale)

    total_w = count * fw + (count - 1) * 60
    start_x = (1920 - total_w) // 2
    phone_y = 180

    for i in range(count):
        x = start_x + i * (fw + 60)
        url = screenshot_urls[i] if i < len(screenshot_urls) else None

        # Frame
        els.append({"id": uid(), "type": "shape", "content": "#0a0a0a",
                     "x": x, "y": phone_y, "width": fw, "height": fh,
                     "borderRadius": int(50 * phone_scale), "zIndex": 10 + i * 3})

        if url:
            els.append({"id": uid(), "type": "image", "content": url,
                         "x": x + border_s, "y": phone_y + border_s,
                         "width": sw, "height": sh,
                         "borderRadius": int(36 * phone_scale), "zIndex": 11 + i * 3})
        else:
            els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                         "x": x + border_s, "y": phone_y + border_s,
                         "width": sw, "height": sh,
                         "borderRadius": int(36 * phone_scale),
                         "opacity": 0.5, "zIndex": 11 + i * 3})

    return els, bg


# ── Physical-product showcase ─────────────────────────────

_SECTOR_DIGITAL = {"app", "saas", "software", "plataforma", "pwa", "mobile", "móvil", "digital", "online"}
_SECTOR_PHYSICAL = {"tienda", "producto", "bebida", "comida", "moda", "café", "artesanal", "ropa", "cosméticos"}
_SECTOR_SERVICE = {"servicio", "consultora", "clínica", "agencia", "consultoría", "estudio"}


def detect_showcase_type(brand: dict) -> str:
    """Detect the kind of product showcase needed for a brand.

    Returns one of: ``digital_product``, ``physical_product``,
    ``service_space``, or ``generic``.
    """
    haystack = " ".join([
        brand.get("sector", ""),
        brand.get("tagline", ""),
        brand.get("description", ""),
        " ".join(brand.get("value_props", [])),
    ]).lower()

    if any(t in haystack for t in _SECTOR_DIGITAL):
        return "digital_product"
    if any(t in haystack for t in _SECTOR_PHYSICAL):
        return "physical_product"
    if any(t in haystack for t in _SECTOR_SERVICE):
        return "service_space"
    return "generic"


def is_digital_product(brand: dict) -> bool:
    """Convenience check: True when the brand describes a digital product."""
    return detect_showcase_type(brand) == "digital_product"


def build_product_showcase_no_screenshots(
    slide: dict,
    palette: dict,
    logo_url: str | None,
    mood_kit: str = "BOLD",
) -> tuple[list[dict], str]:
    """Fallback product_showcase for digital products without screenshots.

    Layout: centred logo on a white backdrop + title + 3 feature columns.
    Richer than the plain phone-placeholder so the slide doesn't look empty.
    """
    is_dark = mood_kit in ("BOLD", "EDITORIAL")
    bg = palette.get("foreground", "#0F172A") if is_dark else palette["background"]
    text_color = "#FAFAFA" if is_dark else palette["foreground"]
    muted_color = "rgba(255,255,255,0.6)" if is_dark else muted(palette)

    els: list[dict] = []

    # Background shape
    els.append({"id": uid(), "type": "shape", "content": bg,
                "x": 0, "y": 0, "width": 1920, "height": 1080, "zIndex": 0})

    # Title centred at top
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 120, "width": 1760, "height": 100,
                "fontSize": 64, "fontWeight": "900", "color": text_color,
                "textAlign": "center", "zIndex": 30})

    # Logo backdrop card
    els.append({"id": uid(), "type": "shape", "content": "#FAFAFA",
                "x": 710, "y": 340, "width": 500, "height": 400,
                "borderRadius": 32, "opacity": 0.95, "zIndex": 20})

    # Logo centred inside backdrop
    if logo_url:
        els.append({"id": uid(), "type": "image", "content": logo_url,
                     "x": 810, "y": 440, "width": 300, "height": 200,
                     "zIndex": 21})

    # Feature columns at bottom (up to 3)
    body = slide.get("body_items", [])
    col_positions = [(160, 400), (760, 400), (1360, 400)]
    for i, item in enumerate(body[:3]):
        x, w = col_positions[i]
        els.append({"id": uid(), "type": "text", "content": item,
                     "x": x, "y": 820, "width": w, "height": 120,
                     "fontSize": 24, "fontWeight": "500", "color": muted_color,
                     "textAlign": "center", "zIndex": 30})

    return els, bg


def build_physical_product_hero(
    slide: dict,
    product_image_url: str | None,
    palette: dict,
    logo_url: str | None,
    mood_kit: str = "EDITORIAL",
) -> tuple[list[dict], str]:
    """Build a product_showcase slide for a physical product.

    Layout: product image on the left + title/features on the right.
    """
    is_dark = mood_kit in ("BOLD", "EDITORIAL")
    bg = palette.get("foreground", "#0F172A") if is_dark else palette["background"]
    text_color = "#FAFAFA" if is_dark else palette["foreground"]
    muted_color = "rgba(255,255,255,0.6)" if is_dark else muted(palette)

    els: list[dict] = []

    # Decorative circle behind product (low opacity)
    els.append({"id": uid(), "type": "shape", "content": palette["primary"],
                "x": -100, "y": 200, "width": 800, "height": 800,
                "opacity": 0.15, "zIndex": 1})

    # Product image or logo placeholder
    if product_image_url:
        els.append({"id": uid(), "type": "image", "content": product_image_url,
                     "x": 120, "y": 140, "width": 760, "height": 800,
                     "zIndex": 10})
    elif logo_url:
        els.append({"id": uid(), "type": "image", "content": logo_url,
                     "x": 260, "y": 340, "width": 400, "height": 400,
                     "zIndex": 10})

    # Title
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 960, "y": 200, "width": 880, "height": 180,
                "fontSize": 64, "fontWeight": "900", "color": text_color, "zIndex": 30})

    # Subtitle
    sub = slide.get("subtitle", "")
    if sub:
        els.append({"id": uid(), "type": "text", "content": sub,
                     "x": 960, "y": 400, "width": 880, "height": 80,
                     "fontSize": 24, "fontWeight": "400", "color": muted_color, "zIndex": 31})

    # Feature bullets (up to 3)
    body = slide.get("body_items", [])
    for i, item in enumerate(body[:3]):
        y = 520 + i * 90
        els.append({"id": uid(), "type": "shape", "content": palette.get("accent", palette["primary"]),
                     "x": 960, "y": y + 8, "width": 12, "height": 12,
                     "zIndex": 32 + i * 2})
        els.append({"id": uid(), "type": "text", "content": item,
                     "x": 988, "y": y, "width": 840, "height": 70,
                     "fontSize": 22, "fontWeight": "400", "color": muted_color,
                     "zIndex": 33 + i * 2})

    return els, bg


def build_product_grid(
    slide: dict,
    image_urls: list[str],
    product_palette: dict,
    logo_url: str | None,
    mood_kit: str = "EDITORIAL",
) -> tuple[list[dict], str]:
    """Build a product_showcase slide as a 2×2 image grid.

    Works for physical products or service spaces with multiple images.
    """
    is_dark = mood_kit in ("BOLD", "EDITORIAL")
    bg = product_palette.get("foreground", "#0F172A") if is_dark else product_palette["background"]
    text_color = "#FAFAFA" if is_dark else product_palette["foreground"]

    els: list[dict] = []

    # Title top
    els.append({"id": uid(), "type": "text", "content": slide.get("title", ""),
                "x": 80, "y": 40, "width": 1760, "height": 100,
                "fontSize": 56, "fontWeight": "900", "color": text_color,
                "textAlign": "center", "zIndex": 60})

    count = min(len(image_urls), 4)
    if count == 0:
        if logo_url:
            els.append({"id": uid(), "type": "image", "content": logo_url,
                         "x": 760, "y": 340, "width": 400, "height": 400,
                         "zIndex": 10})
        return els, bg

    cols = 2
    img_w = 800
    img_h = 420
    gap = 40
    total_w = cols * img_w + (cols - 1) * gap
    start_x = (1920 - total_w) // 2
    start_y = 180

    for i, url in enumerate(image_urls[:4]):
        c = i % cols
        r = i // cols
        x = start_x + c * (img_w + gap)
        y = start_y + r * (img_h + gap)
        els.append({"id": uid(), "type": "image", "content": url,
                     "x": x, "y": y, "width": img_w, "height": img_h,
                     "zIndex": 10 + i})

    return els, bg
