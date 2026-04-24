"""LLM-powered content generator for social media posts.

Two-pass architecture:
  Pass 1 — Nova Pro Vision analyses logo + product images (once per job).
  Pass 2 — GLM-5 generates copy + image_prompt for N posts (one LLM call).

The old ``_call_nova()`` helper is kept for backward-compat with other
callers (vision_analyzer, video_generator) but is no longer used here.
"""

import asyncio
import base64
import json

import httpx

from app.providers import bedrock

from app.core.logging import get_logger
from app.services.template_generator import _get_bedrock_client  # reuse same boto3 client
from app.config import settings

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

CONTENT_PROMPT = """\
Eres un director creativo senior de una agencia de publicidad de clase mundial.
Genera contenido para posts de redes sociales que sean ESPECÍFICOS y BRILLANTES.

IDIOMA OBLIGATORIO:
GENERA TODO EL COPY EN {language_full}.
Headlines, body, CTAs, hashtags — TODO en {language_full}.
Los image_prompts van SIEMPRE en inglés (es lo que entienden mejor los modelos de imagen),
PERO si el image_prompt incluye texto a renderizar sobre la imagen,
ese texto específico va en {language_full}.

ANÁLISIS DE LA MARCA:
- Nombre: {brand_name}
- Logo: {logo_description}
- Estilo del logo: {logo_style}
- Personalidad: {logo_personality}
- Mood: {logo_mood}
- Colores: primario {color_primary}, secundario {color_secondary}, acento {color_accent}

ANÁLISIS DEL PRODUCTO:
- Tipo: {product_type}
- Descripción: {product_description}
- Características: {product_features}
- Estilo visual: {product_style}
- Mejores ángulos: {product_angles}
- Escenarios ideales: {product_settings}
- Estilo fotográfico: {product_photography}

CAMPAÑA DEL CLIENTE:
- Descripción: {campaign_description}
- Tono: {tone}
- Extras: {extras}

PLATAFORMA: {platform}
FORMATO: {format}
NÚMERO DE POSTS: {num_posts}

GENERA {num_posts} posts diferentes. Cada post debe tener:

1. "headline": Frase IMPACTANTE y ESPECÍFICA para ESTA marca (max 6 palabras).
   Usa el mood y personalidad del análisis del logo.
   NO uses frases genéricas. Cada headline debe ser único y memorable.
   Se usará como CAPTION del post (texto debajo de la imagen en Instagram).

2. "body": Texto complementario (1-2 oraciones, máximo 100 caracteres) que conecte
   con el producto REAL. Se usará como CAPTION del post.

3. "cta": Call to action corto y directo (máximo 4 palabras).
   Se usará como CAPTION del post.

4. "image_prompt": Descripción de la escena donde va el producto.

   REGLA PRINCIPAL — LA ESCENA DEBE REFLEJAR LA CAMPAÑA:
   La descripción de la campaña es: "{campaign_description}"
   CADA image_prompt debe crear una escena que VISUALMENTE comunique este mensaje.
   No basta con poner el producto en un lugar bonito — la escena debe contar la HISTORIA de la campaña.

   Ejemplos de cómo adaptar la escena a la campaña:
   - Si la campaña es "celebrar mi primer cliente":
     → Escenas de CELEBRACIÓN: brindis, champagne, confetti, personas levantando copas, ambiente festivo
     → NO escenas genéricas de producto en escritorio o en la calle
   - Si la campaña es "lanzamiento de producto":
     → Escenas de ANTICIPACIÓN y NOVEDAD: unboxing, revelación dramática, spotlight, exclusividad
   - Si la campaña es "descuento de temporada":
     → Escenas de URGENCIA y OPORTUNIDAD: colores llamativos, ambiente de shopping, temporada relevante
   
   PIENSA: "¿Esta escena comunica el mensaje de la campaña?" Si la respuesta es no, cambia la escena.

   REGLA ABSOLUTA: NO incluir texto, letras, palabras ni writing en la imagen.

   USA los escenarios ideales y el estilo fotográfico del análisis del producto.
   Cada prompt debe ser una escena DIFERENTE de la lista de escenarios ideales.

   REGLAS DE CALIDAD:
   - Cada post debe tener una escena DIFERENTE y ÚNICA
   - No repetir escenarios (si uno es "bar counter", otro NO puede ser "bar counter")
   - Variar: ángulos (frontal, overhead flat lay, 45 grados, close-up)
   - Variar: iluminación (warm amber, neon, natural daylight, candles, golden hour)
   - Variar: mood (elegant, fun, intimate, energetic, chill)
   - Ser ESPECÍFICO con detalles visuales (materiales, texturas, colores de ambiente)
   - El producto del cliente se proporcionará como imagen de referencia.
   - Empieza SIEMPRE con "This product" para que Flux sepa qué es la referencia.
   - Describe: dónde está el producto, qué hay alrededor, iluminación, ambiente.
   - NO describas el producto mismo (Flux ya tiene la foto real).
   - Escribe el prompt en INGLÉS.
   - Si el producto es digital (app, website), describe la escena con un teléfono
     mostrando la app. Si es físico, describe el producto en un escenario real.

   REGLAS DE COLOR Y PALETA (CRÍTICAS):
   - La escena DEBE reflejar la paleta de la marca:
     * Color primario {color_primary} — debe dominar la escena (iluminación, elementos principales, fondo)
     * Color secundario {color_secondary} — acentos, objetos de fondo, superficies
     * Color acento {color_accent} — detalles, highlights, pequeños elementos
   - Describe la escena CON la atmósfera de esos colores. Ejemplo: si el primario es
     naranja cálido (#FF6B35), describe "warm orange ambient lighting, golden hour tones,
     orange-tinted surfaces".
   - Si la paleta es de tonos neutros/grises, describe escenas con materiales crudos:
     piedra, concreto, acero, madera envejecida, tonos tierra.
   - NUNCA uses colores que choquen con la paleta de la marca.

   TERMINA SIEMPRE con: "professional commercial product photography, sharp focus on product,
   absolutely no text, no words, no letters, no writing anywhere in the image"

5. "style_description": Estilo visual de la imagen (2-3 palabras).
   Ejemplos: "audaz y vibrante", "minimalista oscuro", "festivo y colorido".

RESPONDE SOLO EN JSON. Sin markdown, sin explicaciones. Exactamente un array de {num_posts} objetos:
[
  {{
    "headline": "...",
    "body": "...",
    "cta": "...",
    "image_prompt": "...",
    "style_description": "..."
  }}
]"""


# ---------------------------------------------------------------------------
# Internal LLM call (sync, run inside asyncio.to_thread)
# NOTE: _call_nova() is no longer used for content generation (now GLM-5).
# It is still used internally by vision_analyzer.py and video_generator.py.
# ---------------------------------------------------------------------------

def _call_nova(prompt_text: str) -> str:
    client = _get_bedrock_client()
    body = json.dumps({
        "system": [{"text": (
            "You are a senior creative director and social media marketing expert. "
            "Always respond with valid JSON only. Never wrap your response in markdown code fences."
        )}],
        "messages": [{"role": "user", "content": [{"text": prompt_text}]}],
        "inferenceConfig": {
            "maxTokens": 4096,
            "temperature": 0.8,
            "topP": 0.9,
        },
    })
    response = client.invoke_model(
        modelId=settings.template_model_id,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


def _parse_json_response(text: str) -> list[dict]:
    """Extract and parse a JSON array from LLM output."""
    text = text.strip()

    # Strip optional markdown fences
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to locate the array inside surrounding prose
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise ValueError("LLM did not return valid JSON")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def _fetch_image_bytes(url_or_b64: str) -> bytes:
    """Download an image URL or decode a base64 data-URL to raw bytes."""
    if url_or_b64.startswith("data:"):
        # data:image/png;base64,xxxxx
        _, encoded = url_or_b64.split(",", 1)
        return base64.b64decode(encoded)
    if url_or_b64.startswith("http"):
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url_or_b64)
            resp.raise_for_status()
            return resp.content
    # Assume raw base64
    return base64.b64decode(url_or_b64)


async def analyze_brand_visuals(
    logo_url: str | None = None,
    product_image_urls: list[str] | None = None,
) -> str:
    """Pass 1: Nova Pro Vision analyses logo + product images.

    Returns a concise English visual description (1-3 sentences).
    If no images are provided, returns an empty string.
    """
    urls = []
    if logo_url:
        urls.append(logo_url)
    if product_image_urls:
        urls.append(product_image_urls[0])  # Max 1 product to avoid saturation
    if not urls:
        return ""

    images_bytes: list[bytes] = []
    for url in urls:
        try:
            img = await _fetch_image_bytes(url)
            images_bytes.append(img)
        except Exception as exc:
            logger.warning("brand_visual_fetch_failed", url=url[:80], error=str(exc))

    if not images_bytes:
        return ""

    system = (
        "You are a visual brand analyst. Describe what you see "
        "in these brand images: logo, product. Focus on:\n"
        "- Colors and visual style\n"
        "- Product shape and material\n"
        "- Any illustrations or graphical elements\n\n"
        "Be concise (1-3 sentences). Write in English. This description will "
        "inform image generation prompts."
    )

    try:
        result = await bedrock.invoke_vision(
            model_id="us.amazon.nova-pro-v1:0",
            system=system,
            images=images_bytes,
            user_text="Describe these brand visuals in 1-3 sentences.",
            max_tokens=200,
        )
        logger.info("brand_visuals_analyzed", length=len(result))
        return result.strip()
    except Exception as exc:
        logger.error("brand_visual_analysis_failed", error=str(exc))
        return ""


async def enrich_context_from_supabase(
    brand_id: str | None = None,
    draft_id: str | None = None,
) -> tuple[dict, dict, list[dict]]:
    """Fetch persisted brand analysis and product data from Supabase.

    Returns:
        (brand_context, first_product_analysis, products_list)
    """
    from app.services.supabase_client import get_client

    brand_context: dict = {}
    product_analysis: dict = {}
    products: list[dict] = []

    client = get_client()

    if brand_id:
        try:
            logger.info("enrich_brand_query", brand_id=brand_id)
            result = (
                client.table("brands")
                .select("name, vision_analysis, primary_color, secondary_color, accent_color, font_family, logo_url")
                .eq("id", brand_id)
                .execute()
            )
            if result.data:
                brand_context = result.data[0]
            else:
                logger.warning("brand_not_found", brand_id=brand_id)
        except Exception as exc:
            logger.warning("enrich_brand_failed", brand_id=brand_id, error=str(exc))

    if draft_id:
        try:
            draft_result = (
                client.table("parrilla_drafts")
                .select("selected_product_ids")
                .eq("id", draft_id)
                .maybe_single()
                .execute()
            )
            if draft_result.data and draft_result.data.get("selected_product_ids"):
                products_result = (
                    client.table("brand_products")
                    .select("*")
                    .in_("id", draft_result.data["selected_product_ids"])
                    .execute()
                )
                products = products_result.data or []
                if products and products[0].get("vision_analysis"):
                    product_analysis = products[0]["vision_analysis"]
        except Exception as exc:
            logger.warning("enrich_products_failed", draft_id=draft_id, error=str(exc))

    return brand_context, product_analysis, products


async def generate_post_content(
    brand_name: str,
    campaign_description: str,
    tone: str,
    extras: str,
    platform: str,
    format: str,
    num_posts: int,
    brand_colors: dict,
    logo_analysis: dict | None = None,
    product_analysis: dict | None = None,
    language: str = "es",
    visual_context: str = "",
) -> list[dict]:
    """Generate copy + image prompts for *num_posts* social posts.

    Uses GLM-5 (via the Bedrock fallback chain) for creative content
    generation. An optional *visual_context* string (from
    ``analyze_brand_visuals``) is injected into the system prompt.

    Args:
        brand_name:            Client brand / product name.
        campaign_description:  What the product is and the campaign goal.
        tone:                  Desired tone (e.g. "informativo y directo").
        extras:                Hashtags, slogans, or other notes.
        platform:              Target platform (e.g. "instagram").
        format:                Post format key (e.g. "instagram_feed").
        num_posts:             Number of posts to generate.
        brand_colors:          Dict with "primary", "secondary", "accent" hex values.
        logo_analysis:         Vision analysis of the logo (from vision_analyzer).
        product_analysis:      Vision analysis of the product (from vision_analyzer).
        language:              'es' or 'en' — language for generated copy.
        visual_context:        English brand visual description from Pass 1.

    Returns:
        List of dicts, each with keys: headline, body, cta, image_prompt, style_description.
    """
    la = logo_analysis or {}
    pa = product_analysis or {}

    language_full = "español" if language == "es" else "English"

    prompt = CONTENT_PROMPT.format(
        brand_name=brand_name,
        campaign_description=campaign_description,
        extras=extras or "ninguno",
        platform=platform,
        format=format,
        tone=tone,
        num_posts=num_posts,
        language_full=language_full,
        logo_description=la.get("logo_description", "no analizado"),
        logo_style=la.get("style", "no analizado"),
        logo_personality=", ".join(la.get("personality", [])) or "no analizado",
        logo_mood=la.get("mood", "no analizado"),
        color_primary=brand_colors.get("primary", "#000000"),
        color_secondary=brand_colors.get("secondary", "#ffffff"),
        color_accent=brand_colors.get("accent", "#888888"),
        product_type=pa.get("product_type", "no analizado"),
        product_description=pa.get("product_description", "no analizado"),
        product_features=", ".join(pa.get("key_features", [])) or "no analizado",
        product_style=pa.get("style", "no analizado"),
        product_angles=pa.get("best_angles", "no analizado"),
        product_settings=", ".join(pa.get("ideal_settings", [])) or "no analizado",
        product_photography=pa.get("photography_style", "no analizado"),
    )

    # Inject visual context from Pass 1 (if available)
    if visual_context:
        prompt += (
            f"\n\nCONTEXTO VISUAL DE LA MARCA (análisis de imágenes reales):\n"
            f"{visual_context}"
        )

    logger.info("generating_post_content", brand=brand_name, num_posts=num_posts, model="glm-5")

    # GLM-5 via Bedrock fallback chain (GLM-5 → GLM-4.7 → Nova Pro)
    system_prompt = (
        "You are a senior creative director and social media marketing expert. "
        "Always respond with valid JSON only. Never wrap your response in markdown code fences."
    )
    messages = [{"role": "user", "content": [{"text": prompt}]}]

    raw, model_used = await bedrock.invoke_with_fallback(
        system_prompt=system_prompt,
        messages=messages,
        max_tokens=4096,
        temperature=0.8,
    )
    logger.info("content_model_used", model=model_used)

    posts = _parse_json_response(raw)

    if not isinstance(posts, list):
        raise ValueError("Content generator returned non-array JSON")

    # Ensure we have exactly num_posts items (pad or trim)
    if len(posts) < num_posts:
        logger.warning(
            "content_generator_short_response",
            expected=num_posts,
            got=len(posts),
        )
        # Duplicate last item to pad
        while len(posts) < num_posts:
            posts.append(posts[-1])
    posts = posts[:num_posts]

    # Sanitise required keys
    required = {"headline", "body", "cta", "image_prompt", "style_description"}
    for i, post in enumerate(posts):
        for key in required:
            if key not in post:
                post[key] = ""

    logger.info("post_content_generated", brand=brand_name, count=len(posts))
    return posts
