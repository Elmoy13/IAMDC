import asyncio
import base64
import re
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import Browser, Playwright, async_playwright

from app.core.logging import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "posts"

FORMAT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "instagram_feed": (1080, 1080),
    "instagram_story": (1080, 1920),
    "facebook_post": (1200, 630),
    "linkedin_post": (1200, 627),
}

TEMPLATES_METADATA = [
    {
        "id": "bold-center",
        "name": "Bold Center",
        "description": "Headline grande centrado sobre imagen con overlay oscuro",
        "preview_thumbnail": "",
        "supported_formats": [
            "instagram_feed",
            "instagram_story",
            "facebook_post",
            "linkedin_post",
        ],
    },
    {
        "id": "split-left",
        "name": "Split Left",
        "description": "Panel de color a la izquierda con headline y body, imagen a la derecha",
        "preview_thumbnail": "",
        "supported_formats": ["instagram_feed", "facebook_post", "linkedin_post"],
    },
    {
        "id": "minimal-bottom",
        "name": "Minimal Bottom",
        "description": "Imagen fullbleed con barra de primary_color en la parte inferior",
        "preview_thumbnail": "",
        "supported_formats": [
            "instagram_feed",
            "instagram_story",
            "facebook_post",
            "linkedin_post",
        ],
    },
    {
        "id": "card-overlay",
        "name": "Card Overlay",
        "description": "Card blanca centrada sobre imagen con blur de fondo",
        "preview_thumbnail": "",
        "supported_formats": ["instagram_feed", "facebook_post", "linkedin_post"],
    },
]

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# ---------------------------------------------------------------------------
# Playwright singleton
# ---------------------------------------------------------------------------
_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None

# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------
_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    keep_trailing_newline=True,
)


async def start_browser() -> None:
    """Launch the headless Chromium browser.  Called once on app startup."""
    global _playwright, _browser
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(headless=True)
    logger.info("playwright_browser_started")


async def stop_browser() -> None:
    """Close the browser.  Called once on app shutdown."""
    global _playwright, _browser
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass  # already closed / connection lost — safe to ignore
        _browser = None
    if _playwright:
        try:
            await _playwright.stop()
        except Exception:
            pass
        _playwright = None
    logger.info("playwright_browser_stopped")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def render_post(
    template_id: str,
    format: str,
    background_image_b64: str,
    brand: dict,
    copy: dict,
) -> str:
    """Render a social-media post and return a PNG data URL.

    Args:
        template_id:          One of the template IDs (e.g. "bold-center").
        format:               Target social format key (e.g. "instagram_feed").
        background_image_b64: Base64-encoded PNG (raw, without the data: prefix)
                              returned by the image provider.
        brand:                Dict with keys logo_b64, primary_color,
                              secondary_color, font_family.
        copy:                 Dict with keys headline, body, cta.

    Returns:
        ``data:image/png;base64,...``
    """
    if not _browser:
        raise RuntimeError("Playwright browser is not initialised")

    # --- validate inputs -------------------------------------------------------
    if not _SAFE_ID_RE.match(template_id):
        raise ValueError(f"Invalid template_id: {template_id!r}")

    if format not in FORMAT_DIMENSIONS:
        raise ValueError(f"Unsupported format: {format!r}")

    template_file = f"{template_id}.html"
    template_path = TEMPLATES_DIR / template_file
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_id!r}")

    width, height = FORMAT_DIMENSIONS[format]

    # --- normalise image data URLs --------------------------------------------
    bg_data_url = (
        background_image_b64
        if background_image_b64.startswith("data:")
        else f"data:image/png;base64,{background_image_b64}"
    )

    logo_b64 = brand.get("logo_b64", "") or ""
    logo_data_url = (
        logo_b64 if logo_b64.startswith("data:") else f"data:image/png;base64,{logo_b64}"
        if logo_b64
        else ""
    )

    font_family: str = brand.get("font_family") or "Montserrat"
    font_family_url = font_family.replace(" ", "+")

    # --- render template -------------------------------------------------------
    template = _jinja_env.get_template(template_file)
    html = template.render(
        headline=copy.get("headline", ""),
        body=copy.get("body", ""),
        cta=copy.get("cta", ""),
        background_image=bg_data_url,
        logo_url=logo_data_url,
        primary_color=brand.get("primary_color") or "#000000",
        secondary_color=brand.get("secondary_color") or "#ffffff",
        font_family=font_family,
        font_family_url=font_family_url,
        width=width,
        height=height,
    )

    # --- Playwright screenshot -------------------------------------------------
    page = await _browser.new_page(
        viewport={"width": width, "height": height},
        device_scale_factor=2,
    )
    try:
        await page.set_content(html, wait_until="networkidle")
        screenshot_bytes = await page.screenshot(
            type="png",
            clip={"x": 0, "y": 0, "width": width, "height": height},
            full_page=False,
        )
    finally:
        await page.close()

    result_b64 = base64.b64encode(screenshot_bytes).decode()
    logger.info(
        "post_rendered",
        template_id=template_id,
        format=format,
        width=width,
        height=height,
    )
    return f"data:image/png;base64,{result_b64}"


async def render_html_to_png(
    html_content: str,
    width: int,
    height: int,
    device_scale_factor: int = 2,
) -> str:
    """Render an arbitrary HTML string to a PNG data URL via Playwright.

    Args:
        html_content:        Complete HTML document string.
        width:               Viewport width in CSS pixels.
        height:              Viewport height in CSS pixels.
        device_scale_factor: Pixel density multiplier (2 → retina-quality output).

    Returns:
        ``data:image/png;base64,...``
    """
    if not _browser:
        raise RuntimeError("Playwright browser is not initialised")

    page = await _browser.new_page(
        viewport={"width": width, "height": height},
        device_scale_factor=device_scale_factor,
    )
    try:
        await page.set_content(html_content, wait_until="networkidle")
        # Give Google Fonts an extra moment to finish rendering
        await page.wait_for_timeout(1500)
        screenshot_bytes = await page.screenshot(
            type="png",
            clip={"x": 0, "y": 0, "width": width, "height": height},
            full_page=False,
        )
    finally:
        await page.close()

    result_b64 = base64.b64encode(screenshot_bytes).decode()
    logger.info("html_rendered_to_png", width=width, height=height)
    return f"data:image/png;base64,{result_b64}"
