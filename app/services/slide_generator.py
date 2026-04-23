"""Phase 2 — Slide Generator: parallel workers executing the deck plan.

Each slide gets its own LLM call (bounded by semaphore) and receives:
  - The shared creative DNA (from Phase 1)
  - Its specific slide spec from the deck_plan
  - Narrative context (what comes before/after)
"""
import asyncio
import json
import re
import time
from typing import Any

from app.core.logging import get_logger
from app.providers import bedrock, gemini

logger = get_logger(__name__)

# ── Concurrency & timeout settings ────────────────────────

MAX_CONCURRENT_SLIDES = 5  # AWS Bedrock safe concurrency
SLIDE_GENERATION_TIMEOUT = 30  # seconds per slide

# ── Worker system prompt ──────────────────────────────────

SINGLE_SLIDE_SYSTEM = """Eres un diseñador ejecutando UNA slide específica de un deck planificado.
Tienes toda la libertad creativa dentro de los constraints del DNA.

═══ CONTEXTO GLOBAL ═══

DNA Creativo (respétalo estrictamente):
{creative_dna_json}

Marca:
{brand_json}

═══ TU SLIDE ═══

Posición: {position} de {total_slides}
Tipo: {slide_type}
Intent: {intent}
Content brief: {content_brief}
Densidad: {density}
Mood kit: {mood_kit}

Contexto narrativo:
- Slides anteriores: {prev_summary}
- Qué viene después: {next_hint}

═══ FORMATO DE RESPUESTA ═══

Responde EXACTAMENTE un JSON (sin markdown, sin explicación):

{{
  "slide_number": {position},
  "type": "{slide_type}",
  "title": "<título impactante, máx 8 palabras>",
  "subtitle": "<subtítulo o frase de apoyo>",
  "body_items": ["<item1>", "<item2>", ...],
  "image_query": "<búsqueda EN INGLÉS para Unsplash, MUY específica>"
}}

═══ REGLAS POR TIPO ═══

**cover**: title = nombre de marca. subtitle = tagline. body_items = []. image_query = épico del sector.
**manifesto**: title = statement potente. subtitle = apoyo. body_items = []. image_query = emocional.
**problem**: title = frase que capture el dolor. body_items = 3-5 pain points. image_query = emocional.
**solution**: title = frase de transformación. body_items = 3-5 soluciones. image_query = positivo/empowering.
**differentiators**: title = qué te hace único. body_items = 3-4 diferenciadores. image_query = metáfora visual.
**target_persona**: title = "¿Para quién?". body_items = 4-6 datos del buyer persona. image_query = retrato del target.
**competitive_landscape**: title = posicionamiento. body_items = 3-5 comparaciones. image_query = competitivo.
**market_opportunity**: title = oportunidad. body_items = 3-4 datos de mercado. image_query = growth/trends.
**brand_voice**: title = "Así hablamos". body_items = 3-5 reglas de tono. image_query = "".
**brand_visuals**: title = "Dirección de Arte". body_items = []. image_query = moodboard/textura estética.
**product_showcase**: title = copy sobre el producto. subtitle = feature highlight. body_items = 2-3 features clave del producto. image_query = "".
**content_pillars**: title = "Pilares de Contenido". body_items = 3-5 pilares. image_query = "".
**channel_strategy**: title = "Estrategia por Canal". body_items = 3-5 canales + enfoque. image_query = "".
**kpis_objectives**: title = "Métricas de Éxito". body_items = 4-6 KPIs. image_query = "".
**roadmap**: title = "Roadmap". body_items = 3-6 fases. image_query = "".
**cta_final**: title = call to action. subtitle = motivación. body_items = []. image_query = "".

═══ CALIDAD ═══
• Títulos: JAMÁS genéricos. SÍ creativos y conectados al brand brief.
• body_items: concretos, accionables, sin repetir. USA datos del content brief.
• image_query: composición + sujeto + estilo + iluminación (NO "professional team").
• Todos los textos en el idioma de la marca. image_query SIEMPRE en inglés.
• Si density es sparse → 0-3 body_items. medium → 3-5. dense → 5-7.
• Si prev slide era sparse → puedes ser dense (o viceversa) — mantén ritmo.

═══ REGLAS DE SHAPES DECORATIVOS ═══
Si agregas un shape decorativo (blob, círculo grande, rectángulo de fondo), DEBE cumplir:
• Si ocupa >15% del canvas (1920×1080): opacity máximo 0.3 Y zIndex < 10.
• NUNCA tapar un título (text con fontSize >= 60).
• Los shapes grandes van DETRÁS del contenido principal, no encima.
• Si quieres usar un shape como "acento" (15-25% del canvas): opacity máximo 0.5.
• Si necesitas un color sólido de fondo completo, ponlo como backgroundColor, NO como shape encima.
Ejemplos CORRECTOS:
  ✅ Círculo grande primary con opacity 0.2 detrás del título como glow
  ✅ Blob orgánico accent con opacity 0.3 sangrado por un borde
Ejemplos INCORRECTOS:
  ❌ Shape primary 800x600 con opacity 1.0 en medio del canvas
  ❌ Bloque macizo que tapa la mitad del título
  ❌ Shape decorativo con zIndex 50 (debería ser < 10)

═══ REGLA CRÍTICA: NÚMEROS DECORATIVOS GIGANTES ═══
Cuando uses números "01", "02", "03" como elementos DECORATIVOS gigantes de fondo (fontSize >= 120):
✅ OBLIGATORIO:
  - opacity: entre 0.08 y 0.15 (muy sutiles, watermark)
  - zIndex: 0, 1, o 2 (SIEMPRE detrás del contenido)
  - color: puede ser primary, foreground o accent, pero con opacity bajita
❌ PROHIBIDO:
  - opacity >= 0.5 (se vuelven bloques opacos que tapan todo)
  - zIndex >= 5 si hay texto crítico en su bbox
  - fontSize 300+ sin suficiente canvas

Los bullets/títulos asociados al número DEBEN tener zIndex MAYOR (20+).
Ejemplo CORRECTO:
  "01" → fontSize 280, opacity 0.12, zIndex 1
  "Identidad mexicana" → fontSize 32, opacity 1.0, zIndex 20

═══ REGLA DE CONVIVENCIA IMAGEN + CONTENIDO ═══
Si una slide tiene UNA imagen lateral grande (>40% canvas, alineada a un lado):
  - Imagen right (x>=1000): contenido usa x=80 a x=960 (width máx 880)
  - Imagen left (x<920): contenido usa x=960 a x=1840 (width máx 880)
NUNCA configures un bullet/texto con width=1500+ si hay imagen lateral.

═══ REGLA ESPECIAL PARA brand_visuals ═══
Debes mostrar TODOS los colores de marca proporcionados. Si la marca tiene 5 colores, muestra 5 swatches. Si tiene 3, muestra 3. Nunca repitas colores.
Estructura: Grid de N swatches (N = colores en la paleta). Cada swatch con label "Role #HEX".

═══ REGLA ESPECIAL PARA product_showcase ═══
Si la marca no es app/software, NO uses mockup de celular. Describe el producto con title + subtitle + body_items de features. El sistema elegirá el layout correcto según el sector.

═══ REGLAS DE CONTENIDO ═══
• Usa SOLO información del content brief y brand data.
• NO inventes datos, estadísticas, ni competidores que no estén en el brief.
• Si el content brief está vacío para un campo, genera copy genérico breve."""


async def generate_single_slide(
    creative_dna: dict,
    slide_spec: dict,
    brand_minimal: dict,
    total_slides: int,
    mood_kit: str,
) -> dict[str, Any]:
    """Generate content for a single slide using the AI model.

    Args:
        creative_dna: The shared DNA from Phase 1.
        slide_spec: Specific slide spec from deck_plan.
        brand_minimal: Compact brand data.
        total_slides: Total number of slides in the deck.
        mood_kit: The mood kit name (BOLD, EDITORIAL, etc.).
    """
    position = slide_spec.get("position", 1)
    slide_type = slide_spec.get("slide_type", "content")

    system = SINGLE_SLIDE_SYSTEM.format(
        creative_dna_json=json.dumps(creative_dna, ensure_ascii=False),
        brand_json=json.dumps(brand_minimal, ensure_ascii=False),
        position=position,
        total_slides=total_slides,
        slide_type=slide_type,
        intent=slide_spec.get("intent", ""),
        content_brief=slide_spec.get("content_brief", ""),
        density=slide_spec.get("density", "medium"),
        mood_kit=mood_kit,
        prev_summary=slide_spec.get("prev_summary") or "(primera slide)",
        next_hint=slide_spec.get("next_hint", ""),
    )

    prompt = f"Genera la slide {position} ({slide_type}) del deck."
    messages = bedrock._build_converse_messages(prompt, [])

    try:
        raw, model_used = await bedrock.invoke_with_fallback(
            system_prompt=system,
            messages=messages,
            max_tokens=2048,
        )
        logger.info("slide_gen_model", slide=position, model=model_used)
    except Exception as exc:
        logger.warning("slide_gen_bedrock_fallback", slide=position, error=str(exc))
        raw = await gemini.generate_response(
            system_prompt=system,
            user_message=prompt,
            history=[],
        )

    parsed = _parse_slide_json(raw, position, slide_type)
    logger.info("single_slide_generated", slide=position, type=parsed.get("type"))
    return parsed


async def generate_all_slides(
    art_direction: dict,
    brand_data: dict,
) -> list[dict[str, Any]]:
    """Generate N slides in parallel using the deck plan from Phase 1.

    Uses asyncio.Semaphore to bound concurrency to MAX_CONCURRENT_SLIDES
    and per-slide timeouts for resilience.
    """
    deck_plan = art_direction.get("deck_plan", [])
    if not deck_plan:
        # Legacy fallback: build from layout_rhythm
        deck_plan = _legacy_rhythm_to_plan(art_direction.get("layout_rhythm", []))
    if not deck_plan:
        deck_plan = _default_plan()

    total_slides = len(deck_plan)
    creative_dna = art_direction.get("creative_dna", {})
    mood_kit = art_direction.get("mood_kit", "MINIMAL")

    # Build compact brand data
    brand_minimal = {
        "name": brand_data.get("name", ""),
        "tagline": brand_data.get("tagline", ""),
        "sector": brand_data.get("sector", ""),
        "target_audience": brand_data.get("target_audience", ""),
        "pain_points": brand_data.get("pain_points", []),
        "value_props": brand_data.get("value_props", []),
        "tone": brand_data.get("tone", ""),
        "personality": brand_data.get("personality", ""),
        "colors": brand_data.get("colors", {}),
        "strategies": brand_data.get("strategies", []),
        "cta": brand_data.get("cta", ""),
        "competitors": brand_data.get("competitors", []),
        "kpis": brand_data.get("kpis", []),
        "product_images": brand_data.get("product_images", []),
    }

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SLIDES)
    t0 = time.monotonic()

    async def _bounded(spec: dict) -> dict[str, Any]:
        async with semaphore:
            return await asyncio.wait_for(
                generate_single_slide(
                    creative_dna=creative_dna,
                    slide_spec=spec,
                    brand_minimal=brand_minimal,
                    total_slides=total_slides,
                    mood_kit=mood_kit,
                ),
                timeout=SLIDE_GENERATION_TIMEOUT,
            )

    results = await asyncio.gather(
        *[_bounded(spec) for spec in deck_plan],
        return_exceptions=True,
    )

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    slides: list[dict] = []
    failed = 0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("slide_generation_failed", slide=i + 1, error=str(result))
            spec = deck_plan[i] if i < len(deck_plan) else {}
            slides.append(_fallback_slide(
                spec.get("position", i + 1),
                spec.get("slide_type", "content"),
                brand_data,
            ))
            failed += 1
        else:
            slides.append(result)

    # Sort by slide_number
    slides.sort(key=lambda s: s.get("slide_number", 0))

    logger.info(
        "all_slides_generated",
        total=len(slides),
        failed=failed,
        elapsed_ms=elapsed_ms,
        parallel=total_slides,
    )
    return slides


# ── Legacy / fallback helpers ─────────────────────────────

def _legacy_rhythm_to_plan(rhythm: list[dict]) -> list[dict]:
    """Convert old layout_rhythm format into new deck_plan format."""
    plan: list[dict] = []
    for i, r in enumerate(rhythm):
        plan.append({
            "position": r.get("slide", i + 1),
            "slide_type": r.get("type", "content"),
            "intent": "",
            "content_brief": "",
            "density": "medium",
            "image_mood": r.get("image_mood", ""),
            "prev_summary": None,
            "next_hint": "",
        })
    return plan


def _default_plan() -> list[dict]:
    """Minimal 6-slide fallback when no plan is available."""
    types = ["cover", "problem", "solution", "brand_visuals", "differentiators", "cta_final"]
    return [
        {
            "position": i + 1,
            "slide_type": t,
            "intent": "",
            "content_brief": "",
            "density": "sparse" if t in ("cover", "cta_final") else "medium",
            "image_mood": "epic cinematic brand image" if t == "cover" else "",
            "prev_summary": None,
            "next_hint": "",
        }
        for i, t in enumerate(types)
    ]


def _parse_slide_json(raw: str, index: int, expected_type: str) -> dict[str, Any]:
    """Parse single-slide JSON from AI response."""
    # Code block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            data["slide_number"] = index
            return data
        except json.JSONDecodeError:
            pass

    # Raw JSON
    m2 = re.search(r"(\{[\s\S]*\})", raw)
    if m2:
        text = m2.group(1)
        depth = 0
        for i, ch in enumerate(text):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[: i + 1])
                        data["slide_number"] = index
                        return data
                    except json.JSONDecodeError:
                        break

    logger.error("slide_parse_failed", slide=index, raw=raw[:200])
    return _fallback_slide(index, expected_type, {})


def _fallback_slide(index: int, slide_type: str, brand: dict) -> dict[str, Any]:
    """Minimal fallback for a failed slide generation."""
    return {
        "slide_number": index,
        "type": slide_type,
        "title": brand.get("name", "Slide") if slide_type == "cover" else f"Slide {index}",
        "subtitle": brand.get("tagline", ""),
        "body_items": [],
        "image_query": "",
    }
