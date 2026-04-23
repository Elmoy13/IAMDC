"""Brand Strategy Agent — drives the conversational brief interview and produces slides.

Architecture: Three-phase AI pipeline.
  Pass 1 (chat): Conversational interview to collect brand data.
  Phase 1 (creative director): Generates a unified creative vision / art direction.
  Phase 2 (slide generator): Per-slide parallel generation guided by the vision.
  Phase 3 (postprocess): Contrast fix, logo injection, type normalisation, config extraction.
"""
import json
from typing import Any

from app.config import settings
from app.core.logging import get_logger
from app.providers import bedrock, gemini
from app.services.creative_director import generate_creative_vision
from app.services.image_search_service import search_images
from app.services.slide_builder_v2 import build_presentation
from app.services.slide_generator import generate_all_slides
from app.services.slide_postprocess import postprocess_presentation, extract_config

logger = get_logger(__name__)

# ── System prompt: the agent's personality (Pass 1) ────────
BRAND_AGENT_SYSTEM = """Eres un consultor senior de branding creado por NexusAI. Tu trabajo es EXTRAER información del usuario mediante preguntas específicas para construir un brief completo y generar un pitch-deck.

═══ REGLAS ABSOLUTAS ═══
1. NUNCA inventes colores, pain points, diferenciadores, estrategias, propuestas de valor ni cualquier contenido de la marca. TODO debe venir del usuario.
2. Pregunta UN tema a la vez. No abrumes al usuario con múltiples preguntas de golpe.
3. Si el usuario da respuestas vagas ("no sé", "lo que tú digas"), NO inventes — hazle 2-3 preguntas cerradas con opciones concretas para ayudarlo a decidir.
4. Si el usuario se salta un tema, recuérdale que es importante y vuelve a preguntar antes de avanzar.
5. NUNCA propongas colores inventados a menos que el usuario ESPECÍFICAMENTE pida sugerencias diciendo algo como "sugiere colores" o "no tengo paleta, ayúdame".
6. Si el usuario sube un logo, confírmalo. Si NO ha subido logo, pregúntale explícitamente: "¿Me pasas el logo de tu marca? Puedes arrastrarlo aquí o subirlo con el botón de adjuntos."
7. Hablas en el idioma del usuario (detecta automáticamente).

═══ CHECKLIST DE 10 CAMPOS OBLIGATORIOS ═══
Internamente llevas este checklist. En cada turno revisa qué tienes y qué falta. SOLO datos dichos explícitamente por el usuario cuentan como completados:

1. ✅/❌ **Nombre de marca** — Si no tiene, ayúdalo a generar opciones.
2. ✅/❌ **Sector / industria** — Pregunta con ejemplos: tech, gaming, food, moda, salud…
3. ✅/❌ **Tagline** — la propuesta de valor en 1 línea. Si no tiene, ayúdalo a crear una.
4. ✅/❌ **Público objetivo** — Edad, ubicación, estilo de vida, necesidades.
5. ✅/❌ **Pain points** — Mínimo 3 problemas reales que la marca resuelve. DEBEN venir del usuario.
6. ✅/❌ **Diferenciadores** — Mínimo 3 cosas que hacen única a la marca. DEBEN venir del usuario.
7. ✅/❌ **Tono de voz** — Formal/informal, técnico/simple, divertido/serio. Da opciones.
8. ✅/❌ **Colores de marca** — Pide explícitamente: "¿Cuáles son los colores de tu marca? (hex o descripción, mínimo el color principal y el de fondo)". Si no tiene, PREGUNTA si quiere sugerencias.
9. ✅/❌ **Logo** — Pregunta si tiene logo y pide que lo suba. Si no tiene, marca "sin logo" y sigue.
10. ✅/❌ **Imágenes del producto/servicio** — Después de colores y logo, pregunta:
    • Si es app/software/plataforma digital: "Para que el deck se vea BRUTAL, necesito 2-4 screenshots de la app: pantalla principal, un feature destacado, y opcionalmente onboarding o momento wow. Arrástralos al chat."
    • Si es producto físico: "Súbeme 1-5 fotos del producto, empaque o detalles."
    • Si es servicio: "Súbeme fotos del espacio, equipo o entregables."
    Si el usuario dice que no tiene imágenes o dice "no tengo" / "skip" / "luego", marca como completado y sigue.

═══ CAMPOS OPCIONALES (preguntar si hay tiempo) ═══
10. Call to action específico
11. Personalidad de marca (arquetipo)
12. Estrategias clave (del usuario, no inventadas)
13. Referentes visuales

═══ FLUJO ═══
• Saluda brevemente. Pregunta el nombre de la marca o el tema general.
• Después de cada respuesta del usuario, confirma brevemente lo que entendiste y pregunta sobre el SIGUIENTE campo que falte.
• No hagas resúmenes largos con contenido inventado. Solo confirma lo que el usuario DIJO.
• Si el usuario intenta generar prematuramente ("genera", "dale"), revisa tu checklist: si faltan campos obligatorios, dile CUÁLES faltan y por qué importan. No cedas.

═══ CUANDO TODO ESTÉ COMPLETO ═══
Cuando los 10 campos obligatorios estén llenos CON DATOS DEL USUARIO, di:
"Tengo todo lo necesario. ¿Quieres que genere la presentación o prefieres revisar algún punto?"

Solo cuando el usuario confirme, genera el bloque JSON:

```json
{"action":"generate_presentation","brand":{"name":"...","tagline":"...","sector":"...","target_audience":"...","pain_points":["...","...","..."],"value_props":["...","...","..."],"tone":"...","personality":"...","colors":{"primary":"#hex","secondary":"#hex","accent":"#hex","background":"#hex","foreground":"#hex"},"strategies":["...","...","..."],"cta":"..."}}
```

REGLAS DEL JSON:
• Solo datos reales del usuario, NUNCA placeholders ni inventos.
• colors: usa EXACTAMENTE los colores que el usuario dio. Si solo dio primary, pon primary y deja los demás con defaults neutros (#FAFAFA para background, #161B26 para foreground).
• Si el usuario subió logo, incluye "logo_url" con la URL exacta que el sistema te indicó.
• pain_points y value_props: SOLO los que el usuario mencionó explícitamente.

═══ TONO ═══
• Directo y profesional, no corporativo ni servil.
• Si el usuario es irreverente, espejéalo sin exagerar.
• No pidas "por favor" constantemente ni uses emojis excesivos.

═══ SOBRE IMÁGENES / LOGOS ═══
Si el usuario sube un logo o imagen, el sistema te dirá la URL entre corchetes [SISTEMA: ...].
Confirma que lo recibiste y guárdalo para el JSON final.
No generes URLs de imágenes — el sistema busca fotos automáticamente."""


async def _call_ai(system_prompt: str, user_message: str, history: list[dict]) -> str:
    """Call AI — prefer Bedrock (Nova Pro), fallback to Gemini."""
    try:
        return await bedrock.generate_response(
            system_prompt=system_prompt,
            user_message=user_message,
            history=history,
        )
    except Exception as exc:
        logger.warning("bedrock_fallback_to_gemini", error=str(exc))
        return await gemini.generate_response(
            system_prompt=system_prompt,
            user_message=user_message,
            history=history,
        )


async def chat(
    session_id: str,
    user_message: str,
    history: list[dict],
    logo_url: str | None = None,
    uploaded_images: list[str] | None = None,
) -> dict[str, Any]:
    """Process a user message in the brand agent conversation.

    Returns:
        {
            "reply": str,
            "presentation": list|None,
            "status": "chatting"|"done",
            "extracted_config": dict|None,
            "meta": dict|None,
            "creative_dna": dict|None,
        }
    """
    import time as _time
    # Inject context about uploaded assets
    context_additions = ""
    if logo_url:
        context_additions += f"\n[SISTEMA: El usuario subió su logotipo. La URL del logo es: {logo_url}]"
    if uploaded_images:
        for i, img in enumerate(uploaded_images):
            context_additions += f"\n[SISTEMA: Imagen subida #{i+1}: {img}]"

    actual_message = user_message
    if context_additions:
        actual_message = user_message + context_additions

    # ── Pass 1: Conversational interview ───────────────
    ai_reply = await _call_ai(BRAND_AGENT_SYSTEM, actual_message, history)

    # Check if the agent triggered presentation generation
    presentation = None
    status = "chatting"
    extracted_config = None
    meta = None
    creative_dna = None

    json_block = _extract_json_block(ai_reply)
    if json_block and json_block.get("action") == "generate_presentation":
        brand_data = json_block.get("brand", {})

        # Inject logo if provided — must be absolute URL
        if logo_url and logo_url.startswith("http") and "logo_url" not in brand_data:
            brand_data["logo_url"] = logo_url

        # Inject screenshots and product images from uploaded_images
        if uploaded_images:
            brand_data["screenshots"] = uploaded_images
            brand_data.setdefault("product_images", []).extend(uploaded_images)

        # Clean the AI reply — remove the JSON block for the user
        ai_reply = _clean_reply(ai_reply)

        # ══════════════════════════════════════════════
        # 3-PHASE PIPELINE (adaptive)
        # ══════════════════════════════════════════════
        try:
            t0 = _time.monotonic()

            # ── Phase 1: Creative Director (adaptive plan) ──
            logger.info("phase1_creative_director", brand=brand_data.get("name"))
            art_direction = await generate_creative_vision(brand_data)
            creative_dna = art_direction.get("creative_dna", {})

            # ── Phase 2: Per-slide parallel generation ──
            logger.info(
                "phase2_slide_generation",
                brand=brand_data.get("name"),
                total_slides=art_direction.get("total_slides"),
                mood_kit=art_direction.get("mood_kit"),
            )
            slide_content = await generate_all_slides(art_direction, brand_data)

            # ── Search images based on AI's queries ──
            image_map = await _search_images_for_slides(slide_content, art_direction)

            # ── Build visual slide-deck JSON (templates + mood kit) ──
            presentation = build_presentation(brand_data, slide_content, image_map, art_direction)

            # ── Phase 3: Post-process (contrast, logo, overlaps, DNA) ──
            logger.info("phase3_postprocess", brand=brand_data.get("name"))
            try:
                presentation = postprocess_presentation(presentation, brand_data, creative_dna)
            except Exception as pp_exc:
                import traceback
                logger.error(
                    "phase3_postprocess_failed",
                    error=str(pp_exc),
                    tb=traceback.format_exc(),
                )
                raise

            # ── Extract config for downstream use ──
            extracted_config = extract_config(brand_data, art_direction)

            elapsed_ms = int((_time.monotonic() - t0) * 1000)

            meta = {
                "deck_complexity": art_direction.get("deck_complexity", "SUMMARY"),
                "total_slides": len(presentation),
                "mood_kit": art_direction.get("mood_kit", "MINIMAL"),
                "generation_time_ms": elapsed_ms,
                "slides_generated_in_parallel": art_direction.get("total_slides", len(presentation)),
            }

            status = "done"
            ai_reply = ai_reply or "¡Tu presentación está lista! 🎨"
        except Exception as exc:
            logger.error("pipeline_generation_failed", error=str(exc))
            ai_reply += "\n\n⚠️ Hubo un problema al generar la presentación. Intenta de nuevo diciendo 'genera'."

    return {
        "reply": ai_reply,
        "presentation": presentation,
        "status": status,
        "extracted_config": extracted_config,
        "meta": meta,
        "creative_dna": creative_dna,
    }


async def _search_images_for_slides(
    slide_content: list[dict],
    art_direction: dict | None = None,
) -> dict[int, str]:
    """Search Unsplash for each slide's image_query.

    When the creative director provides ``image_query_intent`` in the
    deck_plan, it's appended to the query for more relevant results.
    """
    image_map: dict[int, str] = {}

    # Build a quick lookup: position → deck_plan spec
    deck_plan = (art_direction or {}).get("deck_plan", [])
    plan_by_pos: dict[int, dict] = {
        spec.get("position", 0): spec for spec in deck_plan
    }

    for slide in slide_content:
        num = slide.get("slide_number", 0)
        query = slide.get("image_query", "")
        if not query:
            continue

        # Enrich query with intent from the deck plan (e.g. "portrait", "product")
        spec = plan_by_pos.get(num, {})
        intent = spec.get("image_query_intent", "")
        if intent and intent.lower() not in query.lower():
            query = f"{query}, {intent}"

        results = await search_images(query, count=1)
        if results:
            image_map[num] = results[0]["url"]
            logger.info("image_found", slide=num, query=query[:50])
        else:
            logger.warning("image_not_found", slide=num, query=query[:50])

    return image_map


def _extract_json_block(text: str) -> dict | None:
    """Extract the JSON action dict from the AI response."""
    import re

    # JSON in code blocks
    pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Raw JSON with action key
    pattern2 = r'(\{"action"\s*:\s*"generate_presentation".*)'
    match2 = re.search(pattern2, text, re.DOTALL)
    if match2:
        try:
            return json.loads(match2.group(1))
        except json.JSONDecodeError:
            # Try to find the balanced braces
            raw = match2.group(1)
            depth = 0
            for i, ch in enumerate(raw):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(raw[:i + 1])
                        except json.JSONDecodeError:
                            break
    return None


def _clean_reply(ai_reply: str) -> str:
    """Remove JSON code block from the chat reply."""
    if "```json" in ai_reply:
        parts = ai_reply.split("```json")
        before = parts[0].strip()
        after_parts = "```".join(parts[1].split("```")[1:]).strip()
        return f"{before}\n{after_parts}".strip()
    elif "```" in ai_reply:
        parts = ai_reply.split("```")
        return "".join(parts[i] for i in range(0, len(parts), 2)).strip()
    return ai_reply
