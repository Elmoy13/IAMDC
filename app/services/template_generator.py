"""AI-powered HTML template generator using Amazon Nova Pro via AWS Bedrock.

Strategy
--------
* The background image is NOT sent to the model (could be 2+ MB of PNG which
  would blow the token budget).  Instead the prompt uses the sentinel string
  ``BACKGROUND_IMAGE_PLACEHOLDER`` and the real data URL is substituted in
  Python after generation — keeping the Bedrock call fast and cheap.
* Model: amazon.nova-pro-v1:0  (Nova family's most capable model).
  Configurable via TEMPLATE_MODEL_ID env variable.
"""

import asyncio
import json
from functools import lru_cache

import boto3

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

FORMAT_DIMENSIONS: dict[str, dict] = {
    "instagram_feed": {"width": 1080, "height": 1080, "name": "Instagram Feed"},
    "instagram_story": {"width": 1080, "height": 1920, "name": "Instagram Story"},
    "facebook_post": {"width": 1200, "height": 630, "name": "Facebook Post"},
    "linkedin_post": {"width": 1200, "height": 627, "name": "LinkedIn Post"},
}

_BG_PLACEHOLDER = "BACKGROUND_IMAGE_PLACEHOLDER"
_LOGO_PLACEHOLDER = "LOGO_URL_PLACEHOLDER"
_MAX_RETRIES = 1


@lru_cache(maxsize=1)
def _get_bedrock_client():
    kwargs = {
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }
    if settings.aws_session_token:
        kwargs["aws_session_token"] = settings.aws_session_token
    return boto3.client("bedrock-runtime", **kwargs)



# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

TEMPLATE_PROMPT = """\
Eres un diseñador gráfico senior especializado en social media. Genera HTML/CSS para un post de redes sociales que se vea PROFESIONAL y listo para publicar.

ESPECIFICACIONES TÉCNICAS OBLIGATORIAS:
- Dimensiones EXACTAS: {width}px de ancho × {height}px de alto
- El HTML root element debe tener EXACTAMENTE estas dimensiones: width:{width}px; height:{height}px; overflow:hidden; position:relative;
- Todo el CSS debe ser inline o dentro de un único <style> tag
- NO usar JavaScript
- Importar Google Font: {font_family} con weights 400, 700, 900 usando: <link href="https://fonts.googleapis.com/css2?family={font_family_url}:wght@400;700;900&display=swap" rel="stylesheet">

IMAGEN DE FONDO:
- Usar el string exacto "{bg_placeholder}" como src del <img class="bg"> o como url() en background-image
- Debe cubrir TODO el canvas: width:100%; height:100%; object-fit:cover; position:absolute; top:0; left:0;
- OBLIGATORIO: Agregar un overlay encima de la imagen para que el texto sea legible:
  * Gradiente oscuro de abajo hacia arriba: linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.4) 40%, rgba(0,0,0,0.1) 70%, transparent 100%)
  * O un overlay semitransparente en la zona del texto
  * El overlay es CRÍTICO — sin él el texto blanco sobre imagen clara no se lee

{logo_section}

TEXTOS — MUY IMPORTANTE:
- NO agregar comillas, ni \u00ab\u00bb, ni "", ni ningún signo de puntuación que no esté en el texto original
- Usar el texto EXACTO proporcionado, sin modificarlo ni agregar nada
- Headline:
  * Font: {font_family}, weight 900, color blanco
  * Tamaño: grande pero que QUEPA sin cortarse (máximo 48px para feed cuadrado, 56px para story vertical)
  * Posición: zona inferior del canvas (tercio inferior)
  * text-shadow: 0 2px 20px rgba(0,0,0,0.5) para contraste extra
  * Máximo 2 líneas — si es muy largo, reducir font-size
  * Padding lateral: 40px mínimo a cada lado (zona segura)
- Body:
  * Font: {font_family}, weight 400, color rgba(255,255,255,0.85)
  * Tamaño: 18px-22px
  * Posición: debajo del headline
  * Máximo 3 líneas
- CTA (Call to Action):
  * Estilo: botón/pill con fondo del COLOR PRIMARIO de la marca ({primary_color})
  * Texto: {contrast_color}, font weight 700, tamaño 16px-18px
  * Bordes redondeados: 25px
  * Padding: 12px 32px
  * Posición: parte inferior del canvas, centrado, con margen inferior de 40px
  * Sombra: 0 4px 15px rgba(0,0,0,0.3)
  * NO agregar comillas ni «» al texto del CTA

COLORES DE MARCA — USARLOS:
- Color primario: {primary_color} → usar en CTA, acentos, líneas decorativas
- Color secundario: {secondary_color} → usar en elementos secundarios si aplica
- Color de acento: {accent_color} → usar en detalles sutiles

LAYOUT GENERAL:
- Zona segura: todo el contenido debe tener mínimo 30px de margen desde cualquier borde
- El headline y body NUNCA deben superponerse con el logo
- Jerarquía visual clara: imagen de fondo → overlay → headline → body → CTA
- Agregar un elemento decorativo sutil con el color primario (línea horizontal de 60px, punto o barra — simple y elegante)
- Estructura HTML OBLIGATORIA:
  <div class="canvas" style="position:relative;width:{width}px;height:{height}px;overflow:hidden">
    <img class="bg" style="position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;z-index:0" src="{bg_placeholder}">
    <div class="overlay" style="position:absolute;top:0;left:0;width:100%;height:100%;z-index:1">
      <!-- Todo el contenido aqui: logo, headline, body, CTA -->
    </div>
  </div>

ESTILO:
- {style_description}

CONTENIDO:
- Headline: {headline}
- Body: {body}
- CTA: {cta}

RESPONDE ÚNICAMENTE CON EL HTML. No markdown, no explicaciones, no bloques de código. Solo el HTML empezando con <!DOCTYPE html>."""


def _build_prompt(
    format: str,
    brand: dict,
    copy: dict,
    style_description: str,
    has_logo: bool,
) -> str:
    dims = FORMAT_DIMENSIONS[format]
    width = dims["width"]
    height = dims["height"]
    font_family = brand.get("font_family") or "Montserrat"
    font_family_url = font_family.replace(" ", "+")

    if has_logo:
        logo_section = (
            "LOGO:\n"
            f'- Usar el string exacto "{_LOGO_PLACEHOLDER}" como src del <img> del logo\n'
            "- Posicionar en la esquina superior DERECHA (no izquierda, para no tapar el headline)\n"
            "- Tamaño del logo: máximo 80px de alto, auto width, manteniendo aspect ratio\n"
            "- Margen desde los bordes: 30px arriba, 30px derecha\n"
            "- Agregar sombra sutil: filter: drop-shadow(0 2px 8px rgba(0,0,0,0.3))"
        )
    else:
        logo_section = "LOGO:\n- No hay logo — no renderizar ningún elemento de logo."

    # Escape any literal curly braces in user-provided copy so .format() doesn't break
    def _esc(s: str) -> str:
        return str(s).replace("{", "{{").replace("}", "}}")

    return TEMPLATE_PROMPT.format(
        width=width,
        height=height,
        font_family=font_family,
        font_family_url=font_family_url,
        bg_placeholder=_BG_PLACEHOLDER,
        logo_section=logo_section,
        primary_color=brand.get("primary_color") or "#FF6B35",
        secondary_color=brand.get("secondary_color") or "#004E89",
        accent_color=brand.get("accent_color") or "#F1FAEE",
        contrast_color=brand.get("contrast_color") or "#FFFFFF",
        style_description=style_description,
        headline=_esc(copy.get("headline", "")),
        body=_esc(copy.get("body", "")),
        cta=_esc(copy.get("cta", "")),
    )


def clean_html_response(html: str) -> str:
    """Normalize raw LLM output to valid HTML."""
    html = html.strip()

    # Strip markdown code fences
    if html.startswith("```html"):
        html = html[7:]
    elif html.startswith("```"):
        html = html[3:]
    if html.endswith("```"):
        html = html[:-3]
    html = html.strip()

    # Find first real HTML token if there is leading prose
    lower = html.lower()
    idx = lower.find("<!doctype")
    if idx == -1:
        idx = lower.find("<html")
    if idx > 0:
        html = html[idx:]

    # Remove decorative quotes that Nova Pro sometimes injects
    html = html.replace("\u00ab", "").replace("\u00bb", "")

    return html


def _post_process(html: str, bg_data_url: str, logo_data_url: str) -> str:
    """Clean LLM response and inject real data URLs."""
    html = clean_html_response(html)

    html = html.replace(_BG_PLACEHOLDER, bg_data_url)
    if logo_data_url:
        html = html.replace(_LOGO_PLACEHOLDER, logo_data_url)

    return html.strip()


# ---------------------------------------------------------------------------
# Bedrock call (sync — runs inside asyncio.to_thread)
# ---------------------------------------------------------------------------

def _invoke_nova(prompt_text: str) -> str:
    client = _get_bedrock_client()
    body = json.dumps({
        "system": [{"text": (
            "You are a senior web designer specializing in social media content. "
            "Return ONLY raw HTML. Never wrap your response in markdown code fences."
        )}],
        "messages": [
            {"role": "user", "content": [{"text": prompt_text}]}
        ],
        "inferenceConfig": {
            "maxTokens": 4096,
            "temperature": 0.7,
            "topP": 0.9,
        },
    })

    response = _get_bedrock_client().invoke_model(
        modelId=settings.template_model_id,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_post_template(
    format: str,
    brand: dict,
    copy: dict,
    style_description: str,
    background_image_b64: str,
) -> str:
    """Generate a complete HTML social-media post via Amazon Nova Pro on Bedrock.

    Args:
        format:               Social format key (e.g. "instagram_feed").
        brand:                Brand profile dict (primary_color, secondary_color,
                              accent_color, font_family, logo_b64).
        copy:                 Dict with headline, body, cta.
        style_description:    Free-text aesthetic description.
        background_image_b64: Background image as data URL or raw base64.

    Returns:
        Complete HTML string with real data URLs injected.
    """
    if format not in FORMAT_DIMENSIONS:
        raise ValueError(f"Unsupported format: {format!r}")

    # Normalise data URLs
    bg_data_url = (
        background_image_b64
        if background_image_b64.startswith("data:")
        else f"data:image/png;base64,{background_image_b64}"
    )

    logo_b64_raw = brand.get("logo_b64", "") or ""
    logo_data_url = (
        logo_b64_raw
        if logo_b64_raw.startswith("data:")
        else (f"data:image/png;base64,{logo_b64_raw}" if logo_b64_raw else "")
    )

    prompt_text = _build_prompt(
        format=format,
        brand=brand,
        copy=copy,
        style_description=style_description,
        has_logo=bool(logo_b64_raw),
    )

    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            raw_html = await asyncio.to_thread(_invoke_nova, prompt_text)
            html = _post_process(raw_html, bg_data_url, logo_data_url)

            if not (html.lower().startswith("<!doctype") or html.lower().startswith("<html")):
                raise ValueError("Model response is not valid HTML")

            logger.info("template_generated", format=format, attempt=attempt)
            return html

        except Exception as exc:
            last_exc = exc
            logger.warning(
                "template_generation_attempt_failed",
                attempt=attempt,
                error=str(exc),
            )
            if attempt >= _MAX_RETRIES:
                break

    raise RuntimeError(
        f"Template generation failed after {_MAX_RETRIES + 1} attempt(s): {last_exc}"
    )
