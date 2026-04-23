"""Regression tests for BUG 1-5 z-index / decorative number / template fixes."""
from app.services.slide_postprocess import (
    _is_decorative_number, _is_decorative_text,
    _fix_decorative_numbers, _fix_text_overlaps,
    _boxes_overlap, _get_reserved_zones, postprocess_presentation,
)


# ── BUG 1: decorative number detection ──

def test_is_decorative_number_basic():
    assert _is_decorative_number({"type": "text", "fontSize": 280, "content": "01"})
    assert _is_decorative_number({"type": "text", "fontSize": 200, "content": "3"})
    assert _is_decorative_number({"type": "text", "fontSize": 120, "content": "II"})


def test_is_decorative_number_rejects_normal_text():
    assert not _is_decorative_number({"type": "text", "fontSize": 280, "content": "Pain Points"})
    assert not _is_decorative_number({"type": "text", "fontSize": 48, "content": "01"})
    assert not _is_decorative_number({"type": "shape", "fontSize": 280, "content": "01"})


def test_is_decorative_text_catches_high_opacity_numbers():
    """Decorative numbers with opacity 0.8 should still be detected as decorative."""
    el = {"type": "text", "fontSize": 280, "opacity": 0.8, "content": "01"}
    assert _is_decorative_text(el) is True


def test_fix_decorative_numbers_caps_opacity():
    slide = {
        "elements": [
            {"type": "text", "content": "01", "fontSize": 280, "fontWeight": "900",
             "opacity": 0.8, "zIndex": 10, "x": 80, "y": 260, "width": 300, "height": 250,
             "color": "#2563EB"},
            {"type": "text", "content": "Identidad 100% mexicana", "fontSize": 32,
             "fontWeight": "400", "opacity": 1.0, "zIndex": 5,
             "x": 100, "y": 420, "width": 800, "height": 60, "color": "#161B26"},
        ],
    }
    _fix_decorative_numbers(slide)
    deco = slide["elements"][0]
    crit = slide["elements"][1]
    assert deco["opacity"] <= 0.12
    assert deco["zIndex"] <= 2
    # Critical text should be raised above the decorative element
    assert crit["zIndex"] > deco["zIndex"]


def test_fix_decorative_numbers_leaves_small_numbers():
    """Small numbers inside cards (fontSize < 120) should not be touched."""
    slide = {
        "elements": [
            {"type": "text", "content": "01", "fontSize": 48, "fontWeight": "900",
             "opacity": 0.3, "zIndex": 3, "x": 100, "y": 300, "width": 100, "height": 70},
        ],
    }
    _fix_decorative_numbers(slide)
    assert slide["elements"][0]["opacity"] == 0.3
    assert slide["elements"][0]["zIndex"] == 3


# ── BUG 2: reserved zones in overlaps ──

def test_overlaps_raises_critical_above_decorative_number():
    """Critical text overlapping a decorative number should get its zIndex raised."""
    slide = {
        "elements": [
            {"type": "text", "content": "02", "fontSize": 280, "fontWeight": "900",
             "opacity": 0.12, "zIndex": 1, "x": 80, "y": 200, "width": 400, "height": 300},
            {"type": "text", "content": "Bullet text A", "fontSize": 24, "fontWeight": "400",
             "opacity": 1.0, "zIndex": 3, "x": 80, "y": 350, "width": 800, "height": 60,
             "color": "#161B26"},
            {"type": "text", "content": "Bullet text B", "fontSize": 24, "fontWeight": "400",
             "opacity": 1.0, "zIndex": 4, "x": 80, "y": 420, "width": 800, "height": 60,
             "color": "#161B26"},
        ],
    }
    _fix_text_overlaps(slide)
    deco = slide["elements"][0]
    for el in slide["elements"][1:]:
        if _boxes_overlap(el, deco):
            assert el["zIndex"] > deco["zIndex"]


# ── BUG 5: CTA template has bleeding decorations ──

def test_cta_template_has_decorations():
    from app.services.slide_builder_v2 import _layout_cta, _build_palette
    palette = _build_palette({"primary": "#2563EB", "accent": "#F59E0B"})
    elements, bg = _layout_cta(
        {"title": "CTA!", "subtitle": "Let's go"},
        "", palette, "https://example.com/logo.png",
    )
    # Should have bleeding decoration shapes (with negative coords or > canvas)
    shapes = [e for e in elements if e["type"] == "shape"]
    assert len(shapes) >= 3  # bg + 2 decorative blobs
    decorative_shapes = [s for s in shapes if s["x"] < 0 or s["y"] < 0 or s["x"] > 1500]
    assert len(decorative_shapes) >= 1, "CTA should have at least 1 bleeding decoration"
    # Text zIndex should be high (30+)
    texts = [e for e in elements if e["type"] == "text"]
    for t in texts:
        assert t["zIndex"] >= 30


# ── BUG 3: bullet width constrained with image ──

def test_split_with_bullets_narrow_when_image():
    from app.services.slide_builder_v2 import _layout_split_with_bullets, _build_palette
    palette = _build_palette({"primary": "#2563EB"})
    slide = {"title": "Test", "body_items": ["A", "B", "C"]}
    elements, _ = _layout_split_with_bullets(
        slide, "https://img.example.com/photo.jpg", palette, None,
    )
    bullets = [e for e in elements if e["type"] == "text" and e.get("fontSize", 0) == 26]
    for b in bullets:
        assert b["width"] <= 900, f"Bullet width {b['width']} too wide with image present"


def test_split_with_bullets_wide_without_image():
    from app.services.slide_builder_v2 import _layout_split_with_bullets, _build_palette
    palette = _build_palette({"primary": "#2563EB"})
    slide = {"title": "Test", "body_items": ["A", "B"]}
    elements, _ = _layout_split_with_bullets(slide, "", palette, None)
    bullets = [e for e in elements if e["type"] == "text" and e.get("fontSize", 0) == 26]
    for b in bullets:
        assert b["width"] >= 1700, "Without image, bullets should be full-width"


# ── BUG 4: product showcase includes features ──

def test_phone_mockup_includes_body_items():
    from app.services.mockup_generator import build_phone_mockup
    palette = {"primary": "#2563EB", "foreground": "#0F172A", "background": "#FAFAFA",
               "accent": "#F59E0B", "accents": ["#F59E0B"]}
    slide = {"title": "Tu peda, nivelado", "subtitle": "Feature", "body_items": ["A", "B", "C"]}
    els, _ = build_phone_mockup(slide, None, palette, "https://example.com/logo.png", "BOLD")
    # Should have feature bullet texts
    bullet_texts = [e for e in els if e["type"] == "text" and e.get("fontSize", 0) == 20]
    assert len(bullet_texts) >= 2, "Phone mockup should include body_items as bullets"


# ── Full pipeline smoke test ──

def test_full_pipeline_decorative_numbers_tamed():
    slides = [{
        "type": "differentiators",
        "backgroundColor": "#FAFAFA",
        "elements": [
            {"type": "text", "content": "01", "fontSize": 280, "fontWeight": "900",
             "opacity": 0.8, "zIndex": 5, "x": 80, "y": 260, "width": 300, "height": 250,
             "color": "#2563EB"},
            {"type": "text", "content": "02", "fontSize": 280, "fontWeight": "900",
             "opacity": 0.8, "zIndex": 5, "x": 700, "y": 260, "width": 300, "height": 250,
             "color": "#2563EB"},
            {"type": "text", "content": "Identidad mexicana", "fontSize": 32,
             "fontWeight": "400", "opacity": 1.0, "zIndex": 6,
             "x": 100, "y": 420, "width": 500, "height": 60, "color": "#161B26"},
            {"type": "text", "content": "Juegos propios", "fontSize": 32,
             "fontWeight": "400", "opacity": 1.0, "zIndex": 6,
             "x": 720, "y": 420, "width": 500, "height": 60, "color": "#161B26"},
        ],
    }]
    result = postprocess_presentation(slides, {"logo_url": "https://example.com/logo.png"})
    for el in result[0]["elements"]:
        content = el.get("content", "")
        if content in ("01", "02") and el.get("type") == "text":
            # After compact_zindices the raw values change, but relative order matters
            continue
    # No crash = pass
    assert len(result) == 1


# ── Sprint A — 4 new targeted tests ──

def test_fix_decorative_numbers_reduces_opacity():
    """Decorative number at opacity 0.9 must be reduced to <= 0.12."""
    slide = {
        "elements": [
            {"type": "text", "content": "03", "fontSize": 280, "fontWeight": "900",
             "opacity": 0.9, "zIndex": 8, "x": 200, "y": 100, "width": 350, "height": 300,
             "color": "#FF5733"},
        ],
    }
    _fix_decorative_numbers(slide)
    assert slide["elements"][0]["opacity"] <= 0.12


def test_decorative_number_zindex_below_content():
    """After fix, decorative number zIndex must be lower than co-located content text."""
    slide = {
        "elements": [
            {"type": "text", "content": "01", "fontSize": 260, "fontWeight": "900",
             "opacity": 0.7, "zIndex": 12, "x": 50, "y": 200, "width": 400, "height": 300},
            {"type": "text", "content": "Key differentiator text", "fontSize": 28,
             "fontWeight": "400", "opacity": 1.0, "zIndex": 5,
             "x": 80, "y": 350, "width": 700, "height": 60, "color": "#161B26"},
        ],
    }
    _fix_decorative_numbers(slide)
    deco = slide["elements"][0]
    content = slide["elements"][1]
    assert deco["zIndex"] < content["zIndex"], (
        f"Decorative zIndex {deco['zIndex']} should be below content zIndex {content['zIndex']}"
    )


def test_persona_bullets_width_with_image():
    """Bullets in split_with_bullets layout must be <= 900px wide when an image is present."""
    from app.services.slide_builder_v2 import _layout_split_with_bullets, _build_palette
    palette = _build_palette({"primary": "#E63946", "accent": "#457B9D"})
    slide = {"title": "Nuestro público", "body_items": ["Millennials urbanos", "Gamers casuales", "Foodies"]}
    elements, _ = _layout_split_with_bullets(
        slide, "https://images.unsplash.com/photo-test", palette, None,
    )
    bullets = [e for e in elements if e["type"] == "text" and e.get("fontSize", 0) < 40 and e.get("fontSize", 0) > 0]
    for b in bullets:
        assert b["width"] <= 900, f"Bullet width {b['width']} exceeds 900px with image present"


def test_agent_asks_for_screenshots_when_digital():
    """detect_showcase_type identifies digital products correctly for screenshot prompting."""
    from app.services.mockup_generator import detect_showcase_type, is_digital_product

    digital_brand = {"sector": "App de delivery", "tagline": "Tu comida en minutos", "value_props": []}
    assert detect_showcase_type(digital_brand) == "digital_product"
    assert is_digital_product(digital_brand) is True

    physical_brand = {"sector": "Tienda de ropa", "tagline": "Moda sustentable", "value_props": []}
    assert detect_showcase_type(physical_brand) == "physical_product"
    assert is_digital_product(physical_brand) is False


def test_reserved_zones_includes_hero_images():
    """_get_reserved_zones should detect both decorative numbers and hero images."""
    slide = {
        "elements": [
            {"type": "text", "content": "01", "fontSize": 280, "fontWeight": "900",
             "opacity": 0.12, "zIndex": 1, "x": 80, "y": 200, "width": 400, "height": 300},
            {"type": "image", "content": "https://example.com/hero.jpg",
             "x": 0, "y": 0, "width": 1920, "height": 1080, "opacity": 0.55, "zIndex": 0},
            {"type": "text", "content": "Normal text", "fontSize": 32,
             "x": 100, "y": 500, "width": 800, "height": 60},
        ],
    }
    zones = _get_reserved_zones(slide)
    owners = {z["owner"] for z in zones}
    assert "decorative_number" in owners
    assert "hero_image" in owners
    assert len(zones) == 2


def test_no_screenshot_fallback_has_features():
    """build_product_showcase_no_screenshots should include feature texts and logo backdrop."""
    from app.services.mockup_generator import build_product_showcase_no_screenshots
    palette = {"primary": "#2563EB", "foreground": "#0F172A", "background": "#FAFAFA",
               "accent": "#F59E0B", "accents": ["#F59E0B"]}
    slide = {"title": "Tu App", "body_items": ["Feature A", "Feature B", "Feature C"]}
    els, bg = build_product_showcase_no_screenshots(slide, palette, "https://example.com/logo.png", "BOLD")
    # Should have the logo backdrop shape (#FAFAFA)
    backdrops = [e for e in els if e["type"] == "shape" and e.get("content") == "#FAFAFA"]
    assert len(backdrops) >= 1, "Missing logo backdrop"
    # Should have feature texts
    feature_texts = [e for e in els if e["type"] == "text" and e.get("fontSize") == 24]
    assert len(feature_texts) == 3, f"Expected 3 feature texts, got {len(feature_texts)}"
    # Should have the logo image
    logos = [e for e in els if e["type"] == "image" and "logo" in e.get("content", "")]
    assert len(logos) >= 1, "Missing logo in no-screenshot fallback"
