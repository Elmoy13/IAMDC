"""Regression tests for BUG 1-3 fixes + MEJORA 1 showcase detection."""
from app.services.slide_postprocess import (
    _fix_decorative_shapes, _is_decorative_text, _boxes_overlap,
    _ensure_brand_visuals_completeness, _fix_text_overlaps,
    postprocess_presentation,
)
from app.services.mockup_generator import detect_showcase_type


def test_bug1_large_shape_tamed():
    slide = {
        "elements": [
            {"type": "shape", "content": "#F59E0B", "x": 600, "y": 200,
             "width": 640, "height": 420, "opacity": 1.0, "zIndex": 50},
            {"type": "text", "content": "BacachitoFeliz", "x": 80, "y": 300,
             "width": 800, "height": 100, "fontSize": 96, "fontWeight": "900",
             "color": "#FAFAFA", "zIndex": 60},
        ],
    }
    _fix_decorative_shapes(slide)
    shape = slide["elements"][0]
    assert shape["opacity"] <= 0.15
    assert shape["zIndex"] < 20


def test_bug1_fullbg_shape_untouched():
    slide = {
        "elements": [
            {"type": "shape", "content": "#2563EB", "x": 0, "y": 0,
             "width": 1920, "height": 1080, "opacity": 1.0, "zIndex": 0},
        ],
    }
    _fix_decorative_shapes(slide)
    assert slide["elements"][0]["opacity"] == 1.0


def test_bug1_small_shape_untouched():
    slide = {
        "elements": [
            {"type": "shape", "content": "#FF0000", "x": 100, "y": 100,
             "width": 12, "height": 12, "opacity": 1.0, "zIndex": 30},
        ],
    }
    _fix_decorative_shapes(slide)
    assert slide["elements"][0]["opacity"] == 1.0
    assert slide["elements"][0]["zIndex"] == 30


def test_bug2_decorative_text_detection():
    dec = {"type": "text", "fontSize": 240, "opacity": 0.2, "content": "02"}
    crit = {"type": "text", "fontSize": 24, "opacity": 1.0, "content": "hello"}
    low_op = {"type": "text", "fontSize": 16, "opacity": 0.1, "content": "bg"}
    assert _is_decorative_text(dec) is True
    assert _is_decorative_text(crit) is False
    assert _is_decorative_text(low_op) is True


def test_bug2_critical_texts_separated():
    slide = {
        "elements": [
            {"type": "text", "content": "02", "x": 80, "y": 80,
             "width": 300, "height": 200, "fontSize": 240, "fontWeight": "900",
             "opacity": 0.15, "color": "#F59E0B", "zIndex": 5},
            {"type": "text", "content": "Contenido repetitivo", "x": 80, "y": 100,
             "width": 800, "height": 60, "fontSize": 28, "fontWeight": "400",
             "color": "#FAFAFA", "zIndex": 30},
            {"type": "text", "content": "Juegos genéricos", "x": 80, "y": 110,
             "width": 800, "height": 60, "fontSize": 28, "fontWeight": "400",
             "color": "#FAFAFA", "zIndex": 31},
        ],
    }
    _fix_text_overlaps(slide)
    critical = [
        e for e in slide["elements"]
        if e["type"] == "text" and e.get("opacity", 1.0) >= 0.25
    ]
    critical.sort(key=lambda e: e["y"])
    for i in range(len(critical) - 1):
        bottom = critical[i]["y"] + critical[i]["height"]
        assert critical[i + 1]["y"] >= bottom + 20


def test_bug3_brand_visuals_completeness():
    slide = {
        "type": "brand_visuals",
        "_raw_type": "brand_visuals",
        "elements": [
            {"type": "shape", "content": "#2563EB", "x": 1100, "y": 250, "width": 140, "height": 140},
            {"type": "shape", "content": "#F59E0B", "x": 1260, "y": 250, "width": 140, "height": 140},
        ],
    }
    brand = {
        "colors": {
            "primary": "#2563EB",
            "accent": "#F59E0B",
            "background": "#FAFAFA",
            "foreground": "#161B26",
        },
    }
    _ensure_brand_visuals_completeness(slide, brand)
    shapes = [e for e in slide["elements"] if e["type"] == "shape" and e.get("width", 0) < 300]
    shown = {e["content"].upper() for e in shapes}
    assert "#FAFAFA" in shown
    assert "#161B26" in shown
    assert len(shown) >= 4


def test_mejora1_showcase_type_detection():
    assert detect_showcase_type({"sector": "app de juegos"}) == "digital_product"
    assert detect_showcase_type({"sector": "café artesanal"}) == "physical_product"
    assert detect_showcase_type({"sector": "consultoría legal"}) == "service_space"
    assert detect_showcase_type({"sector": "otro"}) == "generic"


def test_full_pipeline_shape_tamed():
    slides = [{
        "type": "cover",
        "backgroundColor": "#0F172A",
        "elements": [
            {"type": "shape", "content": "#F59E0B", "x": 500, "y": 100,
             "width": 640, "height": 420, "opacity": 1.0, "zIndex": 50},
            {"type": "text", "content": "Brand Name", "x": 80, "y": 300,
             "width": 800, "height": 100, "fontSize": 96, "fontWeight": "900",
             "color": "#FAFAFA", "zIndex": 60},
        ],
    }]
    result = postprocess_presentation(slides, {"logo_url": "https://example.com/logo.png"})
    shapes = [e for e in result[0]["elements"] if e["type"] == "shape"]
    for s in shapes:
        area = s["width"] * s["height"]
        ratio = area / (1920 * 1080)
        if 0.15 < ratio < 0.95:
            assert s["opacity"] <= 0.3


if __name__ == "__main__":
    test_bug1_large_shape_tamed()
    test_bug1_fullbg_shape_untouched()
    test_bug1_small_shape_untouched()
    test_bug2_decorative_text_detection()
    test_bug2_critical_texts_separated()
    test_bug3_brand_visuals_completeness()
    test_mejora1_showcase_type_detection()
    test_full_pipeline_shape_tamed()
    print("ALL REGRESSION TESTS PASSED")
