import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.logging import get_logger
from app.middleware.auth import get_user_agency
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.template_generator import _get_bedrock_client
from app.services.language_detector import detect_language
from app.config import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _build_system_prompt(
    brand_context: dict | None,
    product_context: dict | None,
    brand_colors: dict | None,
    language: str = "es",
) -> str:
    brand_section = (
        json.dumps(brand_context, indent=2, ensure_ascii=False)
        if brand_context
        else "Sin analizar."
    )
    product_section = (
        json.dumps(product_context, indent=2, ensure_ascii=False)
        if product_context
        else "Sin analizar."
    )
    colors_section = (
        json.dumps(brand_colors, indent=2)
        if brand_colors
        else "Sin detectar."
    )

    lang_instruction = (
        "Responde SIEMPRE en español."
        if language == "es"
        else "Always respond in English."
    )

    return (
        "Eres Nano Banano 🍌, un director creativo joven y profesional.\n\n"
        f"IDIOMA: {lang_instruction}\n\n"
        "REGLAS DE COMUNICACIÓN (MUY IMPORTANTE):\n"
        "- Respuestas CORTAS. Máximo 3 oraciones por mensaje. NUNCA más de 4 líneas.\n"
        "- NUNCA uses bullet points, listas numeradas, ni asteriscos.\n"
        "- NUNCA hagas reportes ni análisis largos.\n"
        "- Habla en español profesional pero cercano y amigable. Como un consultor creativo joven que inspira confianza.\n"
        "- Usa \"perfecto\", \"genial\", \"excelente\", \"listo\", \"vamos\".\n"
        "- NUNCA uses slang como \"wey\", \"chido\", \"neta\", \"a huevo\", \"mijo\", \"compa\".\n"
        "- Puedes tutear al usuario pero mantén un tono respetuoso y profesional.\n"
        "- Usa máximo 1-2 emojis por mensaje.\n"
        "- Haz UNA pregunta a la vez. NUNCA hagas varias preguntas en un mensaje.\n"
        "- NO repitas lo que ya sabes. Si ya analizaste la marca, NO la describas de nuevo.\n"
        "- Sé directo. Ve al grano. No des introducciones largas.\n"
        "- Si el usuario te corrige o te da más contexto, adáptate rápido sin disculpas largas.\n\n"
        f"CONTEXTO DE MARCA (ya lo sabes, NO lo repitas al usuario):\n{brand_section}\n\n"
        f"CONTEXTO DEL PRODUCTO (ya lo sabes, NO lo repitas al usuario):\n{product_section}\n\n"
        f"COLORES: {colors_section}\n\n"
        "EJEMPLOS DE CÓMO DEBES RESPONDER:\n"
        "- Mensaje inicial: \"¡Hola! Ya analicé tu marca y tu producto 🚀 ¿Qué tipo de campaña te gustaría crear?\"\n"
        "- Cuando elige: \"Perfecto, contenido para engagement. ¿Prefieres un estilo más elegante o más divertido? 🎯\"\n"
        "- Cuando da tono: \"Excelente elección. ¿Hay algo más que quieras incluir? Algún hashtag, fecha, descuento...\"\n"
        "- Listo para generar: \"Todo listo. Dale click a Generar cuando quieras 🚀\"\n\n"
        "FLUJO DE CONVERSACIÓN (OBLIGATORIO):\n"
        "Debes hacer MÍNIMO 4 preguntas antes de decir 'listo para generar'. Una pregunta a la vez.\n\n"
        "Pregunta 1 (si no tienes contexto de marca):\n"
        "Pregunta sobre la marca — qué hace, a quién va dirigida, qué la hace especial.\n"
        "Ejemplo: 'Cuéntame un poco sobre tu marca, ¿qué ofrece y quién es tu cliente ideal?'\n\n"
        "Pregunta 2 (sobre la campaña específica):\n"
        "Pregunta sobre el OBJETIVO CONCRETO de esta campaña.\n"
        "NO te conformes con respuestas vagas. Si el usuario dice 'quiero publicitar mi primer cliente', "
        "PREGUNTA MÁS: '¡Felicidades! ¿Quieres mostrar la celebración, agradecer al cliente, "
        "o motivar a otros a unirse?'\n\n"
        "Pregunta 3 (sobre el estilo/tono):\n"
        "Pregunta qué tono quiere: elegante, divertido, emotivo, profesional, etc.\n\n"
        "Pregunta 4 (sobre extras):\n"
        "Pregunta si hay hashtags, fechas, promociones o CTAs específicos.\n\n"
        "SOLO después de las 4 preguntas, di 'Todo listo. Dale click a Generar cuando quieras 🚀'.\n\n"
        "IMPORTANTE: Si el usuario da una respuesta corta o vaga, NO avances al siguiente paso. "
        "Pide más detalle. Ejemplos:\n"
        "- Usuario: 'formal' → 'Perfecto, formal. ¿Quieres algo tipo corporativo o más bien elegante-premium?'\n"
        "- Usuario: 'nope' → 'Ok. ¿Y cómo te gustaría que se vea visualmente? ¿Celebración con champagne, "
        "ambiente de oficina exitosa, o algo diferente?'\n\n"
        "NUNCA hagas esto:\n"
        "- Reportes tipo \"Lo que vi en tu logo: * Diseño: Simple...\"\n"
        "- Listas tipo \"Sugerencias: 1. Para Instagram...\"\n"
        "- Presentaciones largas tipo \"¡Hola! Soy Nano Banano, tu agente creativo de IA...\"\n"
        "- Cualquier mensaje con más de 4 líneas"
    )


def _invoke_chat(system_prompt: str, messages: list[dict]) -> str:
    client = _get_bedrock_client()

    # Bedrock requires the first message to be role "user".
    # Drop leading assistant messages the frontend may include.
    while messages and messages[0]["role"] != "user":
        messages.pop(0)

    if not messages:
        return "¡Hola! Soy Nano Banano 🍌 ¿En qué te puedo ayudar hoy?"

    body = json.dumps({
        "system": [{"text": system_prompt}],
        "messages": [
            {
                "role": m["role"],
                "content": [{"text": m["content"]}],
            }
            for m in messages
        ],
        "inferenceConfig": {
            "maxTokens": 500,
            "temperature": 0.7,
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


@router.post("", response_model=ChatResponse)
async def chat_with_nano_banano(
    payload: ChatRequest,
    agency: dict = Depends(get_user_agency),
) -> ChatResponse:
    """Chat with Nano Banano — Nova Pro with full brand/product context."""

    # Resolve language
    lang = payload.language
    if lang == "auto":
        # Detect from latest user message
        last_user = ""
        for m in reversed(payload.messages):
            if m.role == "user":
                last_user = m.content
                break
        lang = await detect_language(
            campaign_brief=last_user,
        )

    system_prompt = _build_system_prompt(
        brand_context=payload.brand_context,
        product_context=payload.product_context,
        brand_colors=payload.brand_colors,
        language=lang,
    )

    messages = [{"role": m.role, "content": m.content} for m in payload.messages]

    try:
        reply = await asyncio.to_thread(_invoke_chat, system_prompt, messages)
    except Exception as exc:
        logger.error("chat_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Chat failed: {exc}",
        )

    return ChatResponse(reply=reply)
