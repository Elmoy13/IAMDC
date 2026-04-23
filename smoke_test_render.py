"""
Quick smoke test — runs the real Nova Pro → Playwright pipeline.
No Vertex AI needed: generates a gradient background with PIL.

Usage:
    python smoke_test_render.py

Output: smoke_output.png  (abrir con cualquier visor de imágenes)
"""

import asyncio
import base64
import io
import os
import sys

# ── Make sure app/ is importable ────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image, ImageDraw
from dotenv import load_dotenv  # type: ignore

load_dotenv()  # load .env so settings picks up AWS creds

from app.services import template_generator, template_renderer


# ---------------------------------------------------------------------------
# 1. Create a placeholder background image (warm coffee gradient) with PIL
# ---------------------------------------------------------------------------

def _make_gradient_bg(width: int = 1080, height: int = 1080) -> str:
    """Return a base64 PNG of a warm gradient (no Vertex required)."""
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # Simple top→bottom gradient: dark espresso (#1A0A00) → warm latte (#C68642)
    top = (26, 10, 0)
    bottom = (198, 134, 66)
    for y in range(height):
        t = y / height
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# 2. Run the pipeline
# ---------------------------------------------------------------------------

BRAND = {
    "primary_color": "#C68642",
    "secondary_color": "#1A0A00",
    "accent_color": "#F5DEB3",
    "font_family": "Playfair Display",
    "logo_b64": "",
}

COPY = {
    "headline": "El café que despierta tus sentidos",
    "body": "Origen único · Tostado artesanal · Cada sorbo cuenta",
    "cta": "Ordena ahora →",
}


async def main():
    print("🎨  Generando imagen de fondo (gradiente local)...")
    bg_b64 = _make_gradient_bg(1080, 1080)
    print(f"    Imagen lista ({len(bg_b64) // 1024} KB base64)")

    print("\n🤖  Llamando a Amazon Nova Pro via Bedrock...")
    html = await template_generator.generate_post_template(
        format="instagram_feed",
        brand=BRAND,
        copy=COPY,
        style_description="elegante, premium, minimalista — estilo café de especialidad",
        background_image_b64=bg_b64,
    )
    print(f"    HTML generado ({len(html)} chars)")

    # Guardar HTML para inspección
    with open("smoke_output.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("    HTML guardado → smoke_output.html")

    print("\n📸  Renderizando con Playwright (Chromium)...")
    await template_renderer.start_browser()
    try:
        data_url = await template_renderer.render_html_to_png(
            html_content=html,
            width=1080,
            height=1080,
        )
    finally:
        await template_renderer.stop_browser()

    # Decode y guardar PNG
    raw_b64 = data_url.split(",", 1)[1]
    png_bytes = base64.b64decode(raw_b64)
    out_path = os.path.join(os.path.dirname(__file__), "smoke_output.png")
    with open(out_path, "wb") as f:
        f.write(png_bytes)

    size_kb = len(png_bytes) // 1024
    print(f"    PNG guardado → smoke_output.png  ({size_kb} KB)")
    print(f"\n✅  Listo. Abre smoke_output.png para ver el resultado.")


if __name__ == "__main__":
    asyncio.run(main())
