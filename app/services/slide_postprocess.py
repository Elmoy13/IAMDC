"""Post-processing pipeline for slide-deck JSON.

Fixes contrast issues, injects logos on ALL slides, fixes text overlaps,
normalises slide types, and extracts config from the brand brief.
"""
import math
import re
import time
import uuid
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


# ── WCAG contrast helpers ─────────────────────────────────

def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert #RRGGBB to (R, G, B)."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    if len(h) != 6:
        return (0, 0, 0)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG 2.1 relative luminance."""

    def _ch(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)


def _contrast_ratio(c1: str, c2: str) -> float:
    """WCAG contrast ratio between two hex colours."""
    l1 = _relative_luminance(_hex_to_rgb(c1))
    l2 = _relative_luminance(_hex_to_rgb(c2))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _is_hex_color(val: str | None) -> bool:
    """Check if a string looks like #RGB or #RRGGBB."""
    if not val or not isinstance(val, str):
        return False
    v = val.lstrip("#")
    return len(v) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in v)


def _resolve_bg_color(slide: dict) -> str:
    """Determine the effective background colour of a slide."""
    bg = slide.get("backgroundColor", "#ffffff")
    if not _is_hex_color(bg):
        bg = "#ffffff"

    # Check if there's a full-cover opaque image → assume medium luminance
    for el in slide.get("elements", []):
        if el.get("type") == "image":
            w = el.get("width", 0)
            h = el.get("height", 0)
            opacity = el.get("opacity", 1.0)
            if w >= 1800 and h >= 1000 and opacity >= 0.8:
                # Image dominates – return a mid-grey sentinel
                return "#808080"
    return bg


def _ensure_contrast(text_color: str, bg_color: str, min_ratio: float = 4.5) -> str:
    """Return a legible text colour if contrast is too low."""
    if not _is_hex_color(text_color):
        text_color = "#0F172A"
    if not _is_hex_color(bg_color):
        bg_color = "#ffffff"

    ratio = _contrast_ratio(text_color, bg_color)
    if ratio >= min_ratio:
        return text_color

    bg_lum = _relative_luminance(_hex_to_rgb(bg_color))
    if bg_lum > 0.5:
        return "#0F172A"  # dark text on light bg
    else:
        return "#FAFAFA"  # light text on dark bg


# ── Content sanitisation ──────────────────────────────────

def _safe_content(el: dict) -> str:
    """Extract a plain string from an element's content field.

    Workers sometimes return content as a dict ({"text": "..."}) or list
    instead of a bare string. This normalises it defensively.
    """
    content = el.get("content", "")
    if isinstance(content, dict):
        return str(
            content.get("text", "")
            or content.get("value", "")
            or content.get("title", "")
            or next(iter(content.values()), "")
        )
    if isinstance(content, list):
        return " ".join(str(x) for x in content)
    return str(content) if content is not None else ""


def _sanitise_elements(slide: dict) -> None:
    """Ensure every element's content field is a plain string."""
    for el in slide.get("elements", []):
        raw = el.get("content")
        if not isinstance(raw, str):
            el["content"] = _safe_content(el)


# ── Decorative shape detection & fix ──────────────────────

_CANVAS_AREA = 1920 * 1080
_LARGE_SHAPE_THRESHOLD = 0.10  # 10 % of canvas


def _fix_decorative_shapes(slide: dict) -> None:
    """Tame large decorative shapes so they don't overpower content.

    Rules for shapes bigger than 15 % of the canvas:
    1. Opacity capped at 0.3 (decorative, not protagonist).
    2. zIndex forced below 20 so content stays on top.
    3. If the shape overlaps a big title (fontSize >= 60), further reduce
       opacity and reposition the shape away from the title.
    """
    elements = slide.get("elements", [])

    for el in elements:
        if el.get("type") != "shape":
            continue

        w = el.get("width", 0)
        h = el.get("height", 0)
        area = w * h
        ratio = area / _CANVAS_AREA if _CANVAS_AREA else 0

        # Skip small shapes and full-slide bg shapes (100 %)
        if ratio <= _LARGE_SHAPE_THRESHOLD or ratio >= 0.95:
            continue

        opacity = el.get("opacity", 1.0)
        zindex = el.get("zIndex", 0)

        # Rule 1 — cap opacity
        if opacity >= 0.5:
            logger.info("fixing_large_shape_opacity", original=opacity, fixed=0.3)
            el["opacity"] = 0.3

        # Rule 2 — lower zIndex so text wins
        if zindex >= 20:
            el["zIndex"] = 5

        # Rule 3 — avoid collisions with big titles
        for other in elements:
            is_big_title = (
                other.get("type") == "text"
                and other.get("fontSize", 16) >= 60
            )
            if not is_big_title:
                continue
            if not _boxes_overlap(el, other):
                continue

            # Lower opacity further when overlapping a title
            el["opacity"] = min(el.get("opacity", 0.3), 0.15)

            # Reposition shape away from the title zone
            if other.get("x", 0) < 960:  # title on the left
                el["x"] = 1400
                el["y"] = -100
            else:  # title on the right
                el["x"] = -200
                el["y"] = 400
            el["width"] = min(w, 700)
            el["height"] = min(h, 700)
            break  # one reposition per shape is enough


# ── Decorative-text / decorative-number detection ─────────

_DECORATIVE_NUMBER_RE = re.compile(r'^[\dIVXLCDMabc]{1,3}$', re.IGNORECASE)


def _is_decorative_number(el: dict) -> bool:
    """True for giant decorative numbers like '01', '02', 'III', etc.

    Criteria: type==text, fontSize >= 120, content is 1-3 chars matching
    a number or Roman numeral pattern.
    """
    if el.get("type") != "text":
        return False
    if el.get("fontSize", 0) < 120:
        return False
    content = str(el.get("content", "")).strip()
    if len(content) > 3:
        return False
    return bool(_DECORATIVE_NUMBER_RE.match(content))


def _is_decorative_text(el: dict) -> bool:
    """Return True for text elements that are decorative (not critical content).

    Criteria:
    - Giant decorative number (01, 02 etc.) regardless of opacity
    - Huge font (> 200) with low opacity
    - Very low opacity (< 0.25)
    """
    if el.get("type") != "text":
        return False
    if _is_decorative_number(el):
        return True
    opacity = el.get("opacity", 1.0)
    font_size = el.get("fontSize", 16)
    if font_size > 200 and opacity < 0.4:
        return True
    if opacity < 0.25:
        return True
    return False


def _fix_decorative_numbers(slide: dict) -> None:
    """Force giant decorative numbers behind content.

    Rules:
    1. Opacity capped at 0.12 (subtle watermark).
    2. zIndex forced to 1 (behind everything).
    3. Any critical text overlapping gets its zIndex raised.
    """
    elements = slide.get("elements", [])

    critical_texts = [
        e for e in elements
        if e.get("type") == "text"
        and not _is_decorative_number(e)
        and e.get("opacity", 1.0) >= 0.5
    ]

    for el in elements:
        if not _is_decorative_number(el):
            continue

        # Rule 1 — opacity max 0.12
        cur_op = el.get("opacity", 1.0)
        if cur_op > 0.18:
            logger.info("fixing_decorative_number", content=el.get("content"),
                        original_opacity=cur_op)
            el["opacity"] = 0.12

        # Rule 2 — zIndex very low
        if el.get("zIndex", 0) >= 3:
            el["zIndex"] = 1

        # Rule 3 — raise overlapping critical texts above this number
        for ct in critical_texts:
            if _boxes_overlap(el, ct):
                if ct.get("zIndex", 0) <= el.get("zIndex", 0) + 5:
                    ct["zIndex"] = el.get("zIndex", 0) + 10


# ── Brand-visuals palette completeness ────────────────────

def _ensure_brand_visuals_completeness(slide: dict, brand_data: dict) -> None:
    """For brand_visuals slides, make sure all brand colours appear as swatches.

    If colours are missing, inject new swatch elements in a grid below the
    existing ones.
    """
    raw_type = slide.get("_raw_type", slide.get("type", ""))
    if raw_type not in ("brand_visuals", "art_direction", "art"):
        return

    colors = brand_data.get("colors", {})
    if not colors:
        return

    # Collect all expected hex colours from the brand
    expected: dict[str, str] = {}  # upper-hex → role
    for role, val in colors.items():
        if isinstance(val, str) and _is_hex_color(val):
            expected[val.upper()] = role
        elif isinstance(val, dict):
            for sub_role, sub_hex in val.items():
                if isinstance(sub_hex, str) and _is_hex_color(sub_hex):
                    expected[sub_hex.upper()] = f"{role}.{sub_role}"

    if not expected:
        return

    # Find which colours are already shown as small shape swatches
    shown: set[str] = set()
    for el in slide.get("elements", []):
        if el.get("type") == "shape" and el.get("width", 0) < 300:
            c = el.get("content", "")
            if isinstance(c, str) and _is_hex_color(c):
                shown.add(c.upper())

    missing = {h: role for h, role in expected.items() if h not in shown}
    if not missing:
        return

    logger.warning(
        "brand_visuals_incomplete",
        shown=len(shown),
        expected=len(expected),
        missing=list(missing.keys()),
    )

    # Find bottom-most swatch to place new ones below
    max_y = 250
    for el in slide.get("elements", []):
        if el.get("type") == "shape" and el.get("width", 0) < 300:
            bottom = el.get("y", 0) + el.get("height", 0)
            if bottom > max_y:
                max_y = bottom

    swatch_size = 100
    gap = 20
    cols = 4
    start_x = 1100
    start_y = max_y + 40

    for idx, (hex_c, role) in enumerate(missing.items()):
        col_i = idx % cols
        row_i = idx // cols
        x = start_x + col_i * (swatch_size + gap + 40)
        y = start_y + row_i * (swatch_size + 55)

        if y + swatch_size > 1040:
            break  # no room

        slide.setdefault("elements", []).append({
            "id": f"sw-fix-{uuid.uuid4().hex[:4]}",
            "type": "shape",
            "content": hex_c,
            "x": x, "y": y,
            "width": swatch_size, "height": swatch_size,
            "zIndex": 50 + idx * 2,
        })
        slide["elements"].append({
            "id": f"sw-lbl-{uuid.uuid4().hex[:4]}",
            "type": "text",
            "content": f"{role}\n{hex_c}",
            "x": x, "y": y + swatch_size + 4,
            "width": swatch_size + 30, "height": 42,
            "fontSize": 12, "fontWeight": "500",
            "color": "#475569",
            "zIndex": 51 + idx * 2,
        })


# ── Logo injection (ALL slides, collision-aware) ──────────

_CANVAS_W, _CANVAS_H = 1920, 1080
_LOGO_MARGIN = 40

_LOGO_SIZE_BY_TYPE = {
    "cover": 200,
    "cta": 240,
    "art": 180,
    "art_direction": 180,
}
_LOGO_SIZE_DEFAULT = 120


def _slide_has_logo(slide: dict, logo_url: str) -> bool:
    """Check if the slide already contains the logo."""
    for el in slide.get("elements", []):
        if el.get("type") == "image" and el.get("content") == logo_url:
            return True
    return False


def _collides_with_important_elements(logo_box: dict, slide: dict) -> bool:
    """True if logo_box would overlap a title or hero image."""
    for el in slide.get("elements", []):
        is_title = (
            el.get("type") == "text" and el.get("fontSize", 16) >= 40
        )
        is_hero_image = (
            el.get("type") == "image"
            and el.get("width", 0) * el.get("height", 0)
            > _CANVAS_W * _CANVAS_H * 0.4
        )
        if not (is_title or is_hero_image):
            continue
        if _boxes_overlap(logo_box, el):
            return True
    return False


def _find_safe_logo_position(slide: dict, logo_size: int) -> dict:
    """Find a corner that doesn't collide with titles or hero images.

    Priority: top-right > bottom-right > top-left > bottom-left.
    """
    m = _LOGO_MARGIN
    candidates = [
        (_CANVAS_W - logo_size - m, m),            # top-right  (standard pro)
        (_CANVAS_W - logo_size - m, _CANVAS_H - logo_size - m),  # bottom-right
        (m, m),                                     # top-left
        (m, _CANVAS_H - logo_size - m),             # bottom-left
    ]

    for x, y in candidates:
        box = {"x": x, "y": y, "width": logo_size, "height": logo_size}
        if not _collides_with_important_elements(box, slide):
            return box

    # Fallback: top-right (best of bad options — at least won't hide title text)
    return {
        "x": _CANVAS_W - logo_size - m,
        "y": m,
        "width": logo_size,
        "height": logo_size,
    }


def _inject_logo(slide: dict, logo_url: str, slide_type: str) -> None:
    """Add logo element to a slide in a collision-safe position."""
    if not logo_url or not logo_url.startswith("http"):
        return
    if _slide_has_logo(slide, logo_url):
        return

    logo_size = _LOGO_SIZE_BY_TYPE.get(slide_type, _LOGO_SIZE_DEFAULT)
    config = _find_safe_logo_position(slide, logo_size)

    slide.setdefault("elements", []).append({
        "id": f"logo-{int(time.time() * 1000)}-{uuid.uuid4().hex[:4]}",
        "type": "image",
        "content": logo_url,
        "zIndex": 99,
        "opacity": 1.0,
        **config,
    })


# ── Reserved zones ────────────────────────────────────────

def _get_reserved_zones(slide: dict) -> list[dict]:
    """Zones claimed by decorative numbers and hero images.

    Critical texts should not be hidden behind these zones — their
    z-index must be raised above the zone owner when they overlap.
    """
    zones: list[dict] = []
    for el in slide.get("elements", []):
        if _is_decorative_number(el):
            zones.append({
                "x": el["x"], "y": el["y"],
                "width": el["width"], "height": el["height"],
                "owner": "decorative_number",
            })
        elif (
            el.get("type") == "image"
            and el.get("width", 0) * el.get("height", 0)
            > _CANVAS_AREA * 0.4
        ):
            zones.append({
                "x": el["x"], "y": el["y"],
                "width": el["width"], "height": el["height"],
                "owner": "hero_image",
            })
    return zones


# ── Text overlap detection & fix ──────────────────────────

def _estimate_text_height(el: dict) -> int:
    """Estimate real rendered height of a text element based on content length.

    Uses font-weight-aware character width estimation and handles manual
    line breaks (\\n).
    """
    content = _safe_content(el)
    font_size = el.get("fontSize", 16)
    font_weight = str(el.get("fontWeight", "400"))
    width = el.get("width", 1000)

    # Bold / Black fonts are wider
    char_width_factor = 0.55 if font_weight in ("900", "800", "Black", "ExtraBold") else 0.48
    avg_char_width = font_size * char_width_factor
    chars_per_line = max(1, int(width / avg_char_width))

    # Count lines: manual breaks + word wrapping
    manual_lines = content.split("\n")
    total_lines = 0
    for line in manual_lines:
        wrapped = max(1, -(-len(line) // chars_per_line))  # ceil division
        total_lines += wrapped

    line_height = 1.3 if total_lines > 1 else 1.0
    return int(total_lines * font_size * line_height) + 8


def _boxes_overlap(a: dict, b: dict) -> bool:
    """Check if two element bounding boxes overlap vertically and horizontally."""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["width"], ay1 + a["height"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["width"], by1 + b["height"]
    return not (ax2 <= bx1 or bx2 <= ax1 or ay2 <= by1 or by2 <= ay1)


def _fix_text_overlaps(slide: dict) -> None:
    """Detect and fix overlapping elements (v2).

    Pass 1: update estimated heights for multi-line text.
    Pass 2: push overlapping *critical* text pairs apart; shrink font if no room.
           (Decorative texts — watermark numbers, faded labels — are skipped.)
    Pass 3: raise z-index of text hidden behind opaque shapes.
    Pass 4: critical text inside decorative-number zones → raise zIndex.
    Pass 5: critical text inside reserved zones (hero images) → raise zIndex.
    """
    els = slide.get("elements", [])
    canvas_h = 1080

    # ── Pass 1: update estimated heights ──
    text_els = [e for e in els if e.get("type") == "text"]
    for el in text_els:
        estimated = _estimate_text_height(el)
        if estimated > el.get("height", 0):
            el["height"] = estimated

    # ── Pass 2: fix critical text-text overlaps ──
    critical_texts = [
        e for e in text_els if not _is_decorative_text(e)
    ]
    critical_texts.sort(key=lambda e: e.get("y", 0))

    MIN_SPACING = 24
    for i in range(len(critical_texts) - 1):
        current = critical_texts[i]
        next_el = critical_texts[i + 1]

        current_bottom = current["y"] + current["height"]
        if next_el["y"] >= current_bottom + MIN_SPACING:
            continue

        new_y = current_bottom + MIN_SPACING

        # If pushing would overflow, shrink following elements
        if new_y + next_el["height"] > canvas_h:
            for el in critical_texts[i + 1:]:
                cur_fs = el.get("fontSize", 16)
                if cur_fs > 20:
                    el["fontSize"] = max(20, int(cur_fs * 0.85))
                    el["height"] = _estimate_text_height(el)
            new_y = current_bottom + MIN_SPACING

        next_el["y"] = min(new_y, canvas_h - next_el["height"] - 20)

    # ── Pass 3: text hidden behind opaque shapes → raise zIndex ──
    shapes = [e for e in els if e.get("type") == "shape"]
    for text in text_els:
        for shape in shapes:
            if shape.get("zIndex", 0) <= text.get("zIndex", 0):
                continue
            if shape.get("opacity", 1.0) < 0.4:
                continue
            if _boxes_overlap(text, shape):
                text["zIndex"] = shape.get("zIndex", 0) + 10

    # ── Pass 4: critical text inside decorative-number zones → raise zIndex ──
    for text in critical_texts:
        for el in els:
            if not _is_decorative_number(el):
                continue
            if _boxes_overlap(text, el):
                if text.get("zIndex", 0) <= el.get("zIndex", 0) + 5:
                    text["zIndex"] = el.get("zIndex", 0) + 10

    # ── Pass 5: critical text inside reserved zones (hero images) → raise zIndex ──
    reserved = _get_reserved_zones(slide)
    for text in critical_texts:
        for zone in reserved:
            if not _boxes_overlap(text, zone):
                continue
            # Find the owner element to read its zIndex
            owner = next(
                (e for e in els
                 if e.get("x") == zone["x"]
                 and e.get("y") == zone["y"]
                 and e.get("width") == zone["width"]),
                None,
            )
            if owner:
                owner_z = owner.get("zIndex", 0)
                if text.get("zIndex", 0) <= owner_z:
                    text["zIndex"] = owner_z + 10

    # ── Final clamp ──
    for el in text_els:
        if el["y"] + el["height"] > canvas_h:
            el["y"] = max(40, canvas_h - el["height"] - 20)


# ── Slide type normalisation ──────────────────────────────

_TYPE_COLLAPSE = {
    "cover": "cover",
    "cta": "cover",
    "cta_final": "cover",
    "art_direction": "art",
    "art": "art",
    "brand_visuals": "art",
    "problem": "content",
    "value_prop": "content",
    "solution": "content",
    "strategy": "content",
    "content": "content",
    "manifesto": "content",
    "differentiators": "content",
    "target_persona": "content",
    "competitive_landscape": "content",
    "market_opportunity": "content",
    "brand_voice": "content",
    "messaging_architecture": "content",
    "content_pillars": "content",
    "channel_strategy": "content",
    "kpis_objectives": "content",
    "roadmap": "content",
    "product_showcase": "content",
    "team_credits": "content",
}


# ── DNA compliance ────────────────────────────────────────

def _is_dark_color(hex_str: str) -> bool:
    """Return True if a hex colour is perceptually dark (luminance < 0.3)."""
    if not _is_hex_color(hex_str):
        return False
    return _relative_luminance(_hex_to_rgb(hex_str)) < 0.3


def _enforce_dna_compliance(slides: list[dict], creative_dna: dict) -> list[dict]:
    """Validate and correct deviations from the creative DNA."""
    color_usage = creative_dna.get("color_usage", {})
    dark_bg_types = color_usage.get("dark_backgrounds", [])

    for slide in slides:
        raw_type = slide.get("_raw_type", slide.get("type", "content"))

        # Force dark bg on slide types the DNA designates as dark
        if raw_type in dark_bg_types:
            bg = slide.get("backgroundColor", "#ffffff")
            if not _is_dark_color(bg):
                slide["backgroundColor"] = "#161B26"

    return slides


# ── Z-index compaction ────────────────────────────────────

def _compact_zindices(slide: dict) -> dict:
    """Remove z-index gaps and duplicates within a slide."""
    els = slide.get("elements", [])
    if not els:
        return slide
    sorted_els = sorted(els, key=lambda e: (e.get("zIndex", 0), els.index(e)))
    for new_z, el in enumerate(sorted_els):
        el["zIndex"] = new_z
    return slide


# ── extracted_config builder ──────────────────────────────

def extract_config(brand_data: dict, art_direction: dict | None = None) -> dict:
    """Build extracted_config from brand brief data and optional creative vision."""
    colors = brand_data.get("colors", {})
    config = {
        "campaign_name": brand_data.get("name", ""),
        "objective": brand_data.get("objective", "awareness"),
        "audience": brand_data.get("target_audience", ""),
        "tone": brand_data.get("tone", ""),
        "platforms": brand_data.get("platforms", []),
        "key_message": brand_data.get("tagline", ""),
        "call_to_action": brand_data.get("cta", ""),
        "timing": {
            "start_date": None,
            "end_date": None,
            "frequency": None,
        },
        "content_pillars": brand_data.get("strategies", []),
        "hashtags": brand_data.get("hashtags", []),
        "variants_per_post": 2,
        "colors": colors,
        "sector": brand_data.get("sector", ""),
        "personality": brand_data.get("personality", ""),
    }

    # Enrich with creative vision data if available
    if art_direction:
        config["creative_concept"] = art_direction.get("creative_concept", "")
        config["mood"] = art_direction.get("mood", "")
        config["visual_motifs"] = art_direction.get("visual_motifs", [])
        config["dont_do"] = art_direction.get("dont_do", [])

    return config


# ── Public API ────────────────────────────────────────────

def postprocess_presentation(
    slides: list[dict],
    brand_data: dict,
    creative_dna: dict | None = None,
) -> list[dict]:
    """Run all post-processing fixes on a generated slide deck.

    1. Fix text contrast (WCAG 4.5:1 minimum)
    2. Fix text overlaps v2 (text-text + text-shape)
    3. Inject logo on ALL slides (collision-aware)
    4. Enforce DNA compliance (dark backgrounds, etc.)
    5. Compact z-indices
    6. Normalise slide types to cover | content | art
    """
    logo_url = brand_data.get("logo_url")

    for slide in slides:
        # ── 0. Sanitise element content types ─────────
        _sanitise_elements(slide)

        bg_color = _resolve_bg_color(slide)
        raw_type = slide.get("type", "content")
        slide["_raw_type"] = raw_type  # preserve for DNA check

        # ── 1a. Fix decorative numbers (before shapes & overlaps) ──
        _fix_decorative_numbers(slide)

        # ── 1b. Fix decorative shapes ──
        _fix_decorative_shapes(slide)

        # ── 2. Fix text contrast ──────────────────────
        for el in slide.get("elements", []):
            if el.get("type") != "text":
                continue
            color = el.get("color", "")
            if isinstance(color, str) and color.startswith("rgba"):
                continue
            if not _is_hex_color(color):
                continue
            el["color"] = _ensure_contrast(color, bg_color)

        # ── 3. Fix text overlaps (v2 – decorative-aware) ─
        _fix_text_overlaps(slide)

        # ── 4. Inject logo on ALL slides ──────────────
        if logo_url:
            _inject_logo(slide, logo_url, raw_type)

        # ── 5. Brand-visuals palette completeness ─────
        _ensure_brand_visuals_completeness(slide, brand_data)

    # ── 6. DNA compliance (cross-slide) ───────────────
    if creative_dna:
        slides = _enforce_dna_compliance(slides, creative_dna)

    # ── 7. Compact z-indices + collapse types ─────────
    for slide in slides:
        _compact_zindices(slide)
        raw_type = slide.pop("_raw_type", slide.get("type", "content"))
        slide["type"] = _TYPE_COLLAPSE.get(raw_type, "content")

    logger.info("postprocess_done", slides=len(slides))
    return slides
