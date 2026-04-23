"""Tests for postprocess fixes: overlap detection, logo injection on all slides."""
from app.services.slide_postprocess import (
    _fix_text_overlaps,
    _inject_logo,
    _estimate_text_height,
    _boxes_overlap,
    _find_safe_logo_position,
    _collides_with_important_elements,
    postprocess_presentation,
)


def test_overlap_detection_pushes_subtitle_down():
    slide = {
        "type": "cta",
        "elements": [
            {"type": "text", "x": 80, "y": 200, "width": 1760, "height": 100,
             "fontSize": 84, "content": "A long title that wraps multiple lines"},
            {"type": "text", "x": 80, "y": 250, "width": 1760, "height": 80,
             "fontSize": 28, "content": "Subtitle overlapping"},
        ],
    }
    _fix_text_overlaps(slide)
    t1 = slide["elements"][0]
    t2 = slide["elements"][1]
    assert t2["y"] >= t1["y"] + t1["height"]


def test_overlap_clamp_to_canvas():
    slide = {
        "type": "cta",
        "elements": [
            {"type": "text", "x": 80, "y": 900, "width": 1760, "height": 200,
             "fontSize": 84, "content": "Title near bottom"},
            {"type": "text", "x": 80, "y": 950, "width": 1760, "height": 80,
             "fontSize": 28, "content": "Subtitle pushed down"},
        ],
    }
    _fix_text_overlaps(slide)
    for el in slide["elements"]:
        assert el["y"] + el["height"] <= 1100  # within canvas + small margin


def test_boxes_overlap_true():
    a = {"x": 80, "y": 200, "width": 1760, "height": 200}
    b = {"x": 80, "y": 300, "width": 1760, "height": 80}
    assert _boxes_overlap(a, b) is True


def test_boxes_overlap_false():
    a = {"x": 80, "y": 200, "width": 1760, "height": 100}
    b = {"x": 80, "y": 500, "width": 1760, "height": 80}
    assert _boxes_overlap(a, b) is False


def test_logo_injected_on_all_slide_types():
    logo = "https://example.com/logo.png"
    for stype in ["cover", "cta", "art", "art_direction", "content", "problem", "strategy"]:
        slide = {"type": stype, "elements": []}
        _inject_logo(slide, logo, stype)
        logos = [e for e in slide["elements"] if e.get("content") == logo]
        assert len(logos) == 1, f"Logo missing on {stype}"


def test_logo_not_injected_if_relative_url():
    slide = {"type": "cover", "elements": []}
    _inject_logo(slide, "/uploads/logo.png", "cover")
    assert len(slide["elements"]) == 0


def test_logo_not_duplicated():
    logo = "https://example.com/logo.png"
    slide = {"type": "cover", "elements": [
        {"type": "image", "content": logo},
    ]}
    _inject_logo(slide, logo, "cover")
    logos = [e for e in slide["elements"] if e.get("content") == logo]
    assert len(logos) == 1


def test_postprocess_full_pipeline():
    brand = {
        "name": "TestBrand",
        "colors": {"primary": "#2563EB"},
        "logo_url": "https://example.com/logo.png",
    }
    slides = [
        {"type": "cover", "backgroundColor": "#0F172A", "elements": [
            {"type": "text", "x": 80, "y": 580, "width": 1760, "height": 180,
             "fontSize": 96, "fontWeight": "900", "color": "#FAFAFA", "content": "Test"},
        ]},
        {"type": "cta", "backgroundColor": "#2563EB", "elements": [
            {"type": "text", "x": 80, "y": 200, "width": 1760, "height": 300,
             "fontSize": 84, "fontWeight": "900", "color": "#ffffff",
             "content": "Very long CTA title that wraps and wraps and wraps"},
            {"type": "text", "x": 80, "y": 250, "width": 1760, "height": 80,
             "fontSize": 28, "fontWeight": "400", "color": "#ffffff",
             "content": "Overlapping subtitle"},
        ]},
    ]
    result = postprocess_presentation(slides, brand)
    # Logo should be in both slides
    for slide in result:
        logos = [e for e in slide["elements"] if e.get("content") == brand["logo_url"]]
        assert len(logos) >= 1, f"Logo missing in {slide['type']}"
    # CTA texts should not overlap
    cta = result[1]
    texts = [e for e in cta["elements"] if e.get("type") == "text"]
    for i in range(len(texts) - 1):
        a, b = texts[i], texts[i + 1]
        if a["y"] < b["y"]:
            assert b["y"] >= a["y"] + a["height"]


def test_estimate_text_height_long_text():
    el = {"content": "A" * 200, "fontSize": 84, "width": 1760}
    h = _estimate_text_height(el)
    assert h > 84  # Should be more than one line


# ── Collision-aware logo positioning ──────────────────────

def test_logo_avoids_topleft_title():
    """Logo should NOT land at top-left (x=80,y=40) when a title is there."""
    slide = {
        "type": "content",
        "elements": [
            # Title spanning full width at top
            {"type": "text", "x": 80, "y": 60, "width": 1760, "height": 100,
             "fontSize": 56, "content": "El plan para dominar la noche"},
        ],
    }
    pos = _find_safe_logo_position(slide, logo_size=120)
    # Should pick top-right (first candidate), not top-left
    assert pos["x"] > 1000, f"Logo placed at x={pos['x']}, expected top-right"


def test_logo_avoids_fullwidth_title():
    """If title spans full width at top, logo goes to bottom-right or similar."""
    slide = {
        "type": "content",
        "elements": [
            {"type": "text", "x": 0, "y": 0, "width": 1920, "height": 120,
             "fontSize": 56, "content": "Giant wide title"},
        ],
    }
    pos = _find_safe_logo_position(slide, logo_size=120)
    # Both top corners collide with the full-width title, should pick bottom
    assert pos["y"] > 500, f"Logo placed at y={pos['y']}, expected bottom half"


def test_logo_avoids_hero_image():
    """Logo should not overlap a full-bleed hero image (except fallback)."""
    slide = {
        "type": "cover",
        "elements": [
            {"type": "image", "x": 0, "y": 0, "width": 1920, "height": 1080,
             "opacity": 0.55, "content": "https://example.com/hero.jpg"},
        ],
    }
    # Hero covers entire canvas → all positions collide → fallback to top-right
    pos = _find_safe_logo_position(slide, logo_size=200)
    assert pos["x"] == 1920 - 200 - 40  # top-right fallback


def test_logo_prefers_topright():
    """With no obstacles, logo should land at top-right."""
    slide = {"type": "content", "elements": []}
    pos = _find_safe_logo_position(slide, logo_size=120)
    assert pos["x"] == 1920 - 120 - 40
    assert pos["y"] == 40


def test_inject_logo_doesnt_cover_title():
    """End-to-end: inject_logo on a content slide with top-left title."""
    logo = "https://example.com/logo.png"
    slide = {
        "type": "content",
        "elements": [
            {"type": "text", "x": 80, "y": 60, "width": 1760, "height": 100,
             "fontSize": 56, "content": "Lo que ningún otro juego se atreve a hacer"},
        ],
    }
    _inject_logo(slide, logo, "content")
    logo_el = [e for e in slide["elements"] if e.get("content") == logo][0]
    title_el = slide["elements"][0]
    assert not _boxes_overlap(logo_el, title_el), "Logo overlaps the title!"


def test_collides_ignores_small_text():
    """Small text (body, subtitle) should NOT block logo placement."""
    box = {"x": 80, "y": 40, "width": 120, "height": 120}
    slide = {
        "elements": [
            {"type": "text", "x": 80, "y": 50, "width": 800, "height": 60,
             "fontSize": 24, "content": "Small subtitle text"},
        ],
    }
    assert _collides_with_important_elements(box, slide) is False
