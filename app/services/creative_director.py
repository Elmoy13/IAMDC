"""Phase 1 — Creative Director: adaptive deck planner + creative DNA.

Decides how many slides are needed (6-15), which types, the mood kit,
and produces a *creative DNA* document that guides every parallel worker
in Phase 2.
"""
import json
import re
from typing import Any

from app.core.logging import get_logger
from app.providers import bedrock, gemini

logger = get_logger(__name__)

# ── Slide type catalogue (referenced by the prompt) ───────

SLIDE_TYPES_ESSENTIAL = ["cover", "cta_final"]

SLIDE_TYPES_STRATEGIC = [
    "manifesto", "problem", "solution", "differentiators",
    "target_persona", "competitive_landscape", "market_opportunity",
    "brand_voice", "brand_visuals", "product_showcase",
    "messaging_architecture", "content_pillars", "channel_strategy",
    "kpis_objectives", "roadmap", "team_credits",
]

# ── Digital-product detection ─────────────────────────────

_APP_TRIGGERS = [
    "app", "aplicación", "plataforma", "saas", "software",
    "pwa", "móvil", "mobile", "digital", "online",
]


def is_digital_product(brand: dict) -> bool:
    """Detect if the brand describes a digital product / app."""
    haystack = " ".join([
        brand.get("sector", ""),
        brand.get("tagline", ""),
        brand.get("description", ""),
        " ".join(brand.get("value_props", [])),
    ]).lower()
    return any(t in haystack for t in _APP_TRIGGERS)


# ── System prompt ─────────────────────────────────────────

CREATIVE_DIRECTOR_SYSTEM = """Eres un Director Creativo senior. Tu trabajo en este turno es PLANIFICAR un pitch-deck estratégico profesional — NO generar contenido de slides todavía.

Decides:
1. Cuántas slides necesita este deck (entre 6 y 15)
2. Qué slide va en cada posición
3. Qué mood kit visual aplicar
4. Qué DNA creativo comparten todas las slides

MARCA:
{brand_json}

{app_context}

═══ TIPOS DE SLIDES DISPONIBLES ═══

Esenciales (siempre incluir):
- cover: portada con nombre + tagline
- cta_final: call to action de cierre

Estratégicas (usar según complejidad del brief):
- manifesto: statement potente de la marca
- problem: pain points que resuelve
- solution: propuesta de valor (la respuesta al problem)
- differentiators: qué hace único (diferente de value props genéricos)
- target_persona: buyer persona (demográficos + psicografía)
- competitive_landscape: competidores + posicionamiento vs ellos
- market_opportunity: tamaño de mercado, tendencias, timing
- brand_voice: tono, do's and don'ts, ejemplos
- brand_visuals: dirección de arte, paleta, tipografía, mood
- product_showcase: mockups de app/producto digital
- messaging_architecture: mensajes clave por tema
- content_pillars: 3-5 temas/pilares de contenido
- channel_strategy: estrategia por plataforma (IG, TikTok, etc.)
- kpis_objectives: métricas de éxito medibles
- roadmap: timeline de lanzamiento
- team_credits: equipo (si aplica)

═══ COMPLEJIDAD ═══
- SUMMARY (6-8 slides): cover + problem + solution + differentiators + brand_visuals + cta_final
- PROFESSIONAL (9-12 slides): + persona + competitive_landscape + voice + pillars
- EXHAUSTIVE (13-15 slides): + opportunity + messaging + channel_strategy + kpis + roadmap

Determina complejidad según:
- Si el brief menciona competidores → agregar competitive_landscape
- Si menciona KPIs, métricas, objetivos → agregar kpis_objectives
- Si menciona plataformas específicas → agregar channel_strategy
- Si menciona roadmap, fases, timeline → agregar roadmap
- Si es app o producto digital → SIEMPRE agregar product_showcase

═══ MOOD KIT (obligatorio) ═══
Elige UNO:
• BOLD — irreverente, saturado, gen-Z, party. Marcas rebeldes, streetwear, gaming.
• EDITORIAL — premium, lujo, serif, espacio negativo. Moda, beauty, arquitectura.
• PLAYFUL — colorido, geométrico, divertido, pasteles. Apps, food, kids, lifestyle.
• MINIMAL — corporativo, limpio, grid estricto. Tech B2B, consulting, SaaS.

═══ TU RESPUESTA (JSON estricto, sin markdown) ═══

{
  "deck_complexity": "SUMMARY | PROFESSIONAL | EXHAUSTIVE",
  "total_slides": <número entre 6 y 15>,
  "mood_kit": "BOLD | EDITORIAL | PLAYFUL | MINIMAL",
  "mood_reason": "1 línea explicando por qué",
  "creative_dna": {
    "narrative_arc": "Resumen en 2 líneas de la historia del deck",
    "tone_anchors": ["2-3 palabras que definen el tono visual"],
    "color_usage": {
      "primary_role": "para qué se usa el color primario",
      "accent_role": "para qué se usa el accent",
      "dark_backgrounds": ["lista de slide_types con bg oscuro"]
    },
    "typography_system": {
      "hero_size": 140,
      "hero_weight": 900,
      "title_size": 72,
      "subtitle_size": 28,
      "body_size": 24,
      "caption_size": 16
    },
    "visual_motifs": ["motivos recurrentes"],
    "anti_patterns": ["qué NO hacer para esta marca"],
    "image_style": "Descripción del look fotográfico en inglés (para Unsplash)"
  },
  "deck_plan": [
    {
      "position": 1,
      "slide_type": "cover",
      "intent": "Qué debe lograr esta slide",
      "content_brief": "Contenido específico con datos REALES del brief del usuario",
      "density": "sparse | medium | dense",
      "image_mood": "búsqueda EN INGLÉS para Unsplash (o vacío si no necesita imagen)",
      "image_query_intent": "portrait|lifestyle|product|abstract|architecture — tipo de foto necesaria",
      "prev_summary": null,
      "next_hint": "Qué slide viene después"
    }
  ]
}

═══ REGLAS ESTRICTAS ═══
• NO generes contenido de slides, solo el plan.
• CADA slide en deck_plan debe tener content_brief con datos del brief del usuario (no inventados).
• Si el usuario no dio info para un tipo (ej: competidores), NO incluyas esa slide.
• layout_rhythm: alterna densidad para variedad (no todo igual).
• Si mood_kit es BOLD, al menos 30% de slides con bg oscuro o color saturado.
• image_mood SIEMPRE en inglés optimizado para Unsplash. Sé específico (composición + sujeto + estilo).
• Responde SOLO el JSON, sin explicación ni markdown."""


async def generate_creative_vision(brand_data: dict) -> dict[str, Any]:
    """Plan the deck: complexity, slide list, mood kit, and creative DNA.

    Returns the full planning document that drives Phase 2 workers.
    """
    brand_json = json.dumps(brand_data, ensure_ascii=False)

    # Build contextual hints for the prompt
    app_lines: list[str] = []
    if is_digital_product(brand_data):
        app_lines.append("NOTA: Esta marca es un PRODUCTO DIGITAL / APP. Incluye obligatoriamente una slide product_showcase.")
    screenshots = brand_data.get("screenshots", [])
    if screenshots:
        app_lines.append(f"El usuario subió {len(screenshots)} screenshots de la app: {screenshots}")
    app_context = "\n".join(app_lines) if app_lines else ""

    system = CREATIVE_DIRECTOR_SYSTEM.replace("{brand_json}", brand_json).replace("{app_context}", app_context)

    prompt = "Analiza el brief y genera el plan completo del deck."
    messages = bedrock._build_converse_messages(prompt, [])

    try:
        raw, model_used = await bedrock.invoke_with_fallback(
            system_prompt=system,
            messages=messages,
            max_tokens=6000,
        )
        logger.info("creative_director_model", model=model_used)
    except Exception as exc:
        logger.warning("creative_director_bedrock_fallback", error=str(exc))
        raw = await gemini.generate_response(
            system_prompt=system,
            user_message=prompt,
            history=[],
        )

    vision = _parse_vision(raw)

    # Ensure deck_plan exists; build from layout_rhythm for backward compat
    if not vision.get("deck_plan") and vision.get("layout_rhythm"):
        vision["deck_plan"] = _layout_rhythm_to_plan(vision["layout_rhythm"])
    if not vision.get("deck_plan"):
        vision["deck_plan"] = _default_plan(brand_data)

    # Normalise mood_kit
    mk = vision.get("mood_kit", "MINIMAL").upper()
    if mk not in ("BOLD", "EDITORIAL", "PLAYFUL", "MINIMAL"):
        mk = "MINIMAL"
    vision["mood_kit"] = mk

    vision.setdefault("total_slides", len(vision["deck_plan"]))
    vision.setdefault("deck_complexity", _infer_complexity(vision["total_slides"]))
    vision.setdefault("creative_dna", _default_dna())

    logger.info(
        "creative_vision_generated",
        complexity=vision.get("deck_complexity"),
        total_slides=vision.get("total_slides"),
        mood=vision.get("mood_kit"),
    )
    return vision


# ── Parsing / fallbacks ───────────────────────────────────

def _parse_vision(raw: str) -> dict[str, Any]:
    """Extract JSON from the creative director's response."""
    # Try code block first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try raw JSON object (balanced braces)
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
                        return json.loads(text[: i + 1])
                    except json.JSONDecodeError:
                        break

    logger.error("creative_director_parse_failed", raw=raw[:300])
    return {}


def _infer_complexity(n: int) -> str:
    if n <= 8:
        return "SUMMARY"
    if n <= 12:
        return "PROFESSIONAL"
    return "EXHAUSTIVE"


def _layout_rhythm_to_plan(rhythm: list[dict]) -> list[dict]:
    """Convert legacy layout_rhythm entries into deck_plan format."""
    plan: list[dict] = []
    for i, r in enumerate(rhythm):
        plan.append({
            "position": i + 1,
            "slide_type": r.get("type", "content"),
            "intent": "",
            "content_brief": "",
            "density": "medium",
            "image_mood": r.get("image_mood", ""),
            "prev_summary": None if i == 0 else f"slide {i}: {rhythm[i-1].get('type','')}",
            "next_hint": rhythm[i+1].get("type", "") if i + 1 < len(rhythm) else "final",
        })
    return plan


def _default_plan(brand_data: dict) -> list[dict]:
    """Minimal 6-slide fallback when the LLM fails entirely."""
    types = ["cover", "problem", "solution", "brand_visuals", "differentiators", "cta_final"]
    if is_digital_product(brand_data):
        types.insert(-1, "product_showcase")

    plan: list[dict] = []
    for i, t in enumerate(types):
        plan.append({
            "position": i + 1,
            "slide_type": t,
            "intent": "",
            "content_brief": "",
            "density": "sparse" if t in ("cover", "cta_final", "manifesto") else "medium",
            "image_mood": "epic cinematic brand image" if t == "cover" else "",
            "prev_summary": None if i == 0 else f"slide {i}: {types[i-1]}",
            "next_hint": types[i+1] if i + 1 < len(types) else "end",
        })
    return plan


def _default_dna() -> dict:
    """Fallback creative DNA when the LLM doesn't produce one."""
    return {
        "narrative_arc": "From brand challenge to triumphant solution",
        "tone_anchors": ["confident", "modern"],
        "color_usage": {
            "primary_role": "accents and highlights",
            "accent_role": "secondary emphasis",
            "dark_backgrounds": ["cover", "cta_final"],
        },
        "typography_system": {
            "hero_size": 140,
            "hero_weight": 900,
            "title_size": 72,
            "subtitle_size": 28,
            "body_size": 24,
            "caption_size": 16,
        },
        "visual_motifs": ["geometric shapes", "bold typography"],
        "anti_patterns": [],
        "image_style": "modern editorial photography with natural light",
    }
