"""Shared helpers for mood kit layout functions.

All layout functions share this signature:
    (slide: dict, img_url: str, palette: dict, logo_url: str | None)
    -> tuple[list[dict], str]   # (elements, backgroundColor)

Canvas: 1920 × 1080.
"""
import time
import uuid


def uid() -> str:
    return f"el-{int(time.time() * 1000)}-{uuid.uuid4().hex[:4]}"


def text_on_bg(palette: dict, bg: str) -> str:
    from app.services.slide_postprocess import _relative_luminance, _hex_to_rgb
    lum = _relative_luminance(_hex_to_rgb(bg))
    return palette["foreground"] if lum > 0.5 else palette["background"]


def muted(palette: dict) -> str:
    return "#475569"


def rotate_accent(palette: dict, i: int) -> str:
    accents = palette.get("accents", [])
    if not accents:
        return palette["primary"]
    return accents[i % len(accents)]
