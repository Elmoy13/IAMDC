# Auditoría — Community Manager / Messaging

> Fecha: 2026-04-22  
> Alcance: módulo de mensajería, webhooks de Meta, respuestas automáticas con IA  
> Objetivo: mapear el estado actual antes de rearquitectar a multi-tenant + RAG

---

## 1. ARCHIVOS RELACIONADOS

### API / Endpoints
| Archivo | Descripción |
|---------|-------------|
| `app/api/v1/webhook.py` | Webhook de Meta: verificación GET + recepción POST de mensajes |
| `app/api/v1/messages.py` | Endpoints de ai-reply y envío manual de mensajes |
| `app/api/v1/conversations.py` | Toggle del modo de conversación (ai ↔ manual) |
| `app/api/v1/router.py` | Router central que incluye webhook, messages y conversations |

### Servicios
| Archivo | Descripción |
|---------|-------------|
| `app/services/webhook_service.py` | Procesa mensaje entrante: resuelve channel → contact → conversation → guarda Message |
| `app/services/message_service.py` | Genera respuesta IA (con historial), envía vía Meta Graph, guarda en DB. También envío manual |
| `app/services/ai_service.py` | Router de IA: despacha a Gemini o Bedrock según `AI_PROVIDER` |

### Providers
| Archivo | Descripción |
|---------|-------------|
| `app/providers/meta_graph.py` | Envío de mensajes de texto vía Graph API v21.0 |
| `app/providers/gemini.py` | Llamada a Gemini `generateContent` con system prompt + historial |
| `app/providers/bedrock.py` | Llamada a Bedrock Converse API con fallback chain y retry |
| `app/providers/pinecone.py` | **Stub** — clase con métodos `NotImplementedError`. No funcional |

### Modelos de DB (SQLAlchemy)
| Archivo | Descripción |
|---------|-------------|
| `app/db/models/channel.py` | Tabla `channels`: representa una página/canal conectado |
| `app/db/models/contact.py` | Tabla `contacts`: usuario externo que envía mensajes |
| `app/db/models/conversation.py` | Tabla `conversations`: hilo de conversación entre contact y channel |
| `app/db/models/message.py` | Tabla `messages`: mensajes individuales dentro de una conversación |

### Schemas (Pydantic)
| Archivo | Descripción |
|---------|-------------|
| `app/schemas/webhook.py` | Modelos del payload de Meta: `MetaWebhookBody`, `MetaMessagingEntry`, etc. |
| `app/schemas/message.py` | `AIReplyRequest`, `SendMessageRequest`, `MessageResponse` |
| `app/schemas/conversation.py` | `ConversationModeUpdate`, `ConversationModeResponse` |

### Seguridad
| Archivo | Descripción |
|---------|-------------|
| `app/core/security.py` | `verify_meta_signature()` — valida X-Hub-Signature-256 con HMAC SHA256 |
| `app/core/exceptions.py` | Excepciones HTTP: `ChannelNotFoundError`, `MetaSendError`, `WebhookVerificationError`, etc. |

### Tests
| Archivo | Descripción |
|---------|-------------|
| `tests/test_webhook.py` | 2 tests: verificación exitosa y fallida del webhook GET |
| `tests/test_messages.py` | 2 tests: ai-reply y send con conversation inexistente → 404 |

---

## 2. ENDPOINTS EXISTENTES

| Método | Path | Auth | Qué hace | Payload in / out |
|--------|------|------|----------|------------------|
| `GET` | `/api/v1/webhook/meta` | Ninguna | Verificación de webhook de Meta. Valida `hub.verify_token` y devuelve `hub.challenge` | Query: `hub.mode`, `hub.verify_token`, `hub.challenge` → text/plain |
| `POST` | `/api/v1/webhook/meta` | Signature (X-Hub-Signature-256) | Recibe mensajes entrantes de Meta. Procesa cada `entry.messaging`, guarda mensaje, dispara AI reply en background si `mode != "manual"` | Body: `MetaWebhookBody` → `{"status": "ok"}` |
| `POST` | `/api/v1/messages/ai-reply` | **Ninguna** (ver nota) | Genera respuesta IA para una conversación existente y la envía al cliente vía Meta | Body: `AIReplyRequest` {conversation_id, message_text} → `MessageResponse` |
| `POST` | `/api/v1/messages/send` | **Ninguna** (ver nota) | Envía mensaje manual del agente humano al cliente vía Meta | Body: `SendMessageRequest` {conversation_id, message_text} → `MessageResponse` |
| `PATCH` | `/api/v1/conversations/{conversation_id}/mode` | **Ninguna** (ver nota) | Cambia el modo de conversación entre `"ai"` y `"manual"` | Body: `ConversationModeUpdate` {mode} → `ConversationModeResponse` |

> **Nota sobre Auth:** Los tres endpoints de messages y conversations tienen comentarios `TODO` explícitos indicando que no tienen autenticación JWT. El webhook usa solo verificación de firma HMAC. Los endpoints de mensajes están completamente abiertos.

---

## 3. FLUJO ACTUAL END-TO-END

### A. Cuando llega un mensaje de Instagram/Facebook vía webhook

1. Meta envía un `POST` a `/api/v1/webhook/meta` con el payload JSON y header `X-Hub-Signature-256`.
2. FastAPI deserializa el body en `MetaWebhookBody` (Pydantic).
3. Se lee el body raw y se verifica la firma HMAC-SHA256 contra `META_APP_SECRET`. Si falla → 403.
4. Se itera sobre `body.entry[].messaging[]`. Se ignoran entradas sin `.message.text` (no maneja attachments/media).
5. Para cada mensaje con texto:
   - Se extrae `page_id` (recipient.id), `sender_id` (sender.id) y `text`.
   - Se llama a `webhook_service.process_incoming_message(db, page_id, sender_id, text)`.
6. En `webhook_service`:
   - Se busca el `Channel` por `page_id`. Si no existe → 404 `ChannelNotFoundError`.
   - Se busca o crea el `Contact` (por `user_id` del channel + platform + `platform_user_id`).
   - Se busca o crea la `Conversation` (por `contact_id` + `channel_id` + `status="open"`).
   - Se guarda el `Message` (sender=`"customer"`).
   - Se actualiza `last_message_at` en la conversación.
   - Retorna `(conversation_id, message_text, mode)`.
7. De vuelta en el endpoint: si `mode != "manual"`, se encola `_process_ai_reply` como `BackgroundTask`.
8. Se retorna `{"status": "ok"}` inmediatamente (200).

### B. Cómo se genera la respuesta automática

- El background task llama a `message_service.handle_ai_reply(db, conversation_id, message_text)`.
- Se carga la conversación y sus **últimos 10 mensajes** (ordenados por `sent_at DESC`, luego reversed).
- Se construye el `history` como lista de `{"role": sender, "content": content}`.
- Se llama a `ai_service.generate_response(system_prompt, user_message, history)`.
- `ai_service` despacha al provider según `AI_PROVIDER` (env var):
  - `"gemini"` → `gemini.generate_response()`
  - `"bedrock"` → `bedrock.generate_response()`
- **No hay RAG, ni knowledge base, ni info de marca, ni productos, ni FAQ.** Solo el system prompt genérico + los últimos 10 mensajes.

### C. Cómo se envía la respuesta de vuelta

- Se llama a `meta_graph.send_text_message(recipient_id, text, access_token)`.
- USA la Graph API v21.0: `POST https://graph.facebook.com/v21.0/me/messages`
- El `access_token` viene de `conversation.channel.access_token` (almacenado en la tabla `channels`).
- El `recipient_id` viene de `conversation.contact.platform_user_id`.
- `messaging_type` es siempre `"RESPONSE"`.
- Si la API de Meta devuelve un status != 200, se lanza `MetaSendError` (502).

### D. Cómo se maneja el toggle AI ↔ manual

- El estado vive en `conversations.mode` (columna `TEXT`, nullable, sin default explícito en el modelo).
- Se cambia con `PATCH /api/v1/conversations/{id}/mode` pasando `{"mode": "ai"}` o `{"mode": "manual"}`.
- **No hay auth** en ese endpoint — cualquiera puede cambiar el modo.
- Cuando `mode == "manual"`, el webhook simplemente no encola el background task de AI reply. El mensaje entrante se guarda pero no se responde automáticamente.
- Si `mode` es NULL (default para conversaciones nuevas), el AI reply **sí** se dispara (porque `NULL != "manual"`).

### E. Cómo se desactivan respuestas automáticas en Meta

- **No hay ninguna llamada para deshabilitar el chatbot nativo de Meta.** No se maneja el handover protocol ni se desactivan respuestas automáticas de Meta (como los "instant replies" de la página).
- No hay integración con la Handover Protocol API.
- Todo se controla internamente en la columna `mode` de la conversación.

---

## 4. SCHEMA DE DB

### Tabla `channels`

| Columna | Tipo | Nullable | Default |
|---------|------|----------|---------|
| `id` | UUID | NO | `uuid4()` |
| `user_id` | UUID | NO | — |
| `platform` | TEXT | SÍ | — |
| `page_id` | TEXT | SÍ | — |
| `access_token` | TEXT | SÍ | — |
| `phone_number_id` | TEXT | SÍ | — |
| `created_at` | DATETIME | SÍ | `now()` |

- **No tiene `agency_id`**. Usa `user_id` directamente.
- `phone_number_id` sugiere intención futura de WhatsApp Business, pero no se usa en ningún servicio.
- No hay índices explícitos más allá del PK. No hay índice en `page_id` (se busca por este campo en el webhook).
- Foreign keys: ninguna definida a nivel de modelo (el `user_id` no referencia a una tabla de users en SQLAlchemy).
- Relationship: `conversations` (1:N).

### Tabla `contacts`

| Columna | Tipo | Nullable | Default |
|---------|------|----------|---------|
| `id` | UUID | NO | `uuid4()` |
| `user_id` | UUID | NO | — |
| `platform` | TEXT | SÍ | — |
| `platform_user_id` | TEXT | SÍ | — |
| `name` | TEXT | SÍ | — |
| `created_at` | DATETIME | SÍ | `now()` |

- **No tiene `agency_id`**. Usa `user_id`.
- No hay índice único en (`user_id`, `platform`, `platform_user_id`) a pesar de ser la clave de búsqueda. Podría causar duplicados bajo concurrencia.
- Relationship: `conversations` (1:N).

### Tabla `conversations`

| Columna | Tipo | Nullable | Default |
|---------|------|----------|---------|
| `id` | UUID | NO | `uuid4()` |
| `user_id` | UUID | NO | — |
| `contact_id` | UUID | NO | FK → `contacts.id` |
| `channel_id` | UUID | NO | FK → `channels.id` |
| `status` | TEXT | SÍ | `"open"` |
| `mode` | TEXT | SÍ | NULL |
| `last_message_at` | DATETIME | SÍ | — |

- **No tiene `agency_id`**. Usa `user_id`.
- `mode`: sin default en el modelo (NULL). El código trata NULL como "ai activo".
- `status`: solo se filtra por `"open"` para buscar conversaciones activas, pero no hay flujo para cerrar/archivar conversaciones.
- Relationships: `contact` (selectin), `channel` (selectin), `messages` (ordenados por `sent_at`).

### Tabla `messages`

| Columna | Tipo | Nullable | Default |
|---------|------|----------|---------|
| `id` | UUID | NO | `uuid4()` |
| `conversation_id` | UUID | NO | FK → `conversations.id` |
| `sender` | TEXT | SÍ | — |
| `content` | TEXT | SÍ | — |
| `ai_suggestion` | TEXT | SÍ | — |
| `sent_at` | DATETIME | SÍ | `now()` |

- `sender` usa strings libres: `"customer"`, `"ai"`, `"agent"`. No es un enum.
- `ai_suggestion`: columna presente pero **nunca usada** en ningún servicio. Probablemente era para un modo de "sugerencia" que no se implementó.
- No hay columna para media/attachments.
- Relationship: `conversation` (M:1).

### Sobre multi-tenancy

**Ninguna tabla de messaging tiene `agency_id`.** Todas usan `user_id` directamente, que es un UUID de Supabase Auth. Esto implica:
- La asociación es `user → channel`, no `agency → channel`.
- Si un usuario cambia de agencia, sus channels lo siguen a él, no a la agencia.
- No hay RLS policies visible en el código Python (se asume que se manejan en Supabase directamente, pero sin `agency_id` no hay filtro multi-tenant).

### SQL Migrations

No existen migrations de Alembic para las tablas de messaging. Los `.sql` encontrados en `alembic/versions/` son para `post_versions`, `post_edit_chat` y `generation_jobs` — nada relacionado con channels/contacts/conversations/messages. Las tablas de messaging probablemente se crearon manualmente en Supabase.

---

## 5. CONFIG DE META / META GRAPH API

### Variables de entorno

| Variable | Propósito |
|----------|-----------|
| `META_VERIFY_TOKEN` | Token de verificación del webhook (string arbitrario, se compara en el GET) |
| `META_APP_SECRET` | Secret de la Meta App, usado para verificar firmas HMAC-SHA256 |
| `META_PAGE_ACCESS_TOKEN_1` | Page access token, preset en `.env` — **no se usa en el código** |
| `META_PAGE_ACCESS_TOKEN_2` | Otro page access token, preset en `.env` — **no se usa en el código** |

### Almacenamiento de Page Access Tokens

- Los tokens se almacenan **por channel en la tabla `channels.access_token`**.
- Hay dos tokens hardcoded en `.env` (`META_PAGE_ACCESS_TOKEN_1`, `_2`) pero el `Settings` de Pydantic **no los carga** — no hay campos correspondientes en la clase `Settings`. Es decir, son valores residuales/de referencia, no los usa la app.
- En runtime, el sistema lee `conversation.channel.access_token` de la DB para enviar mensajes.
- **No hay refresh de tokens.** Los page access tokens de Meta expiran (los de corto plazo tras 1h, los de largo plazo tras ~60 días). No hay mecanismo de renovación.

### OAuth / Autorización de páginas

- **No existe flujo de OAuth.** No hay endpoint de callback, no hay Login with Facebook, no hay Facebook Login for Business.
- La conexión de una página requiere que alguien inserte manualmente un registro en la tabla `channels` con el `page_id` y el `access_token`.
- No hay UI ni API para este proceso.

### Permisos de Meta App necesarios

No están documentados en el código. Basándose en el uso de `me/messages` y la recepción de webhooks, se necesitan como mínimo:
- `pages_messaging` — para enviar/recibir mensajes de página
- `pages_manage_metadata` — para suscribir webhooks
- Para Instagram DMs: `instagram_manage_messages` (no está claro si se usa)

### Webhook Subscription Management

- **No hay gestión programática de suscripciones.** No hay endpoint ni servicio para crear/eliminar suscripciones de webhook. Se asume configuración manual en el panel de Meta.

---

## 6. IA PARA RESPUESTAS

### Modelo y Provider

- Configurable vía `AI_PROVIDER` env var. Actualmente: `"gemini"`.
- Si `"gemini"`: usa **Gemini 2.5 Flash** (`gemini-2.5-flash`) vía API REST directa.
- Si `"bedrock"`: usa el modelo configurado en `BEDROCK_MODEL_ID` (actualmente `amazon.nova-pro-v1:0`) vía Converse API con fallback chain.

### Contexto que se pasa al modelo

- **Historial de conversación**: últimos 10 mensajes de la conversación, con roles mapeados (`customer` → `user`, `ai`/`agent` → `assistant`/`model`).
- **No se pasa**: información de marca, brief, tono, valores, productos, FAQ, knowledge base. Nada.
- El modelo responde sin contexto de la marca. Es un chatbot genérico de customer service.

### System prompt

Hardcoded en `message_service.py`:

```
"You are a helpful customer service assistant. Reply concisely and professionally in the same language the customer uses. If you don't know the answer, say so honestly."
```

Es idéntico para todas las conversaciones, todas las marcas, todos los canales.

### Parámetros de generación

| Parámetro | Gemini | Bedrock |
|-----------|--------|---------|
| `temperature` | 0.7 | 0.7 |
| `maxOutputTokens` / `maxTokens` | 8192 | 8000 |
| `stop_sequences` | No | No |
| Timeout | 120s (httpx) | 30s (por defecto de Bedrock client) |
| Retries | No | Sí, 3 intentos con backoff exponencial para errores transitorios |
| Concurrency | Sin límite | Semáforo de 5 invocaciones concurrentes |

---

## 7. VECTOR STORE / PINECONE

### `app/providers/pinecone.py`

Existe, pero es un **stub completo**. La clase `PineconeProvider` tiene 3 métodos:
- `upsert_embeddings()` → `raise NotImplementedError`
- `query()` → `raise NotImplementedError`
- `delete()` → `raise NotImplementedError`

### Variables de entorno

```
PINECONE_API_KEY=    # comentado en .env
PINECONE_INDEX=      # comentado en .env
```

Los campos existen en `Settings` con defaults vacíos (`""`), pero no se usan en ningún servicio.

### Otros vector stores

- No hay integración con pgvector, Weaviate, Chroma, ni ningún otro vector store.
- No hay generación de embeddings en el código (ni OpenAI, ni Bedrock Titan, ni Cohere, ni Vertex).
- No hay RAG de ningún tipo implementado.

---

## 8. LIMITACIONES CONOCIDAS

### Multi-tenancy
- **No es multi-tenant.** Las tablas de messaging usan `user_id` (Supabase Auth UID), no `agency_id`. El resto de la app (posts, brands, jobs) sí usa `agency_id` vía Supabase RLS. El módulo de messaging está desconectado de esa arquitectura.
- No se puede filtrar conversations/messages por agencia.

### Múltiples páginas por agencia
- Técnicamente, un usuario puede tener múltiples channels (registros en la tabla). Pero no hay UI, API, ni lógica para gestionarlos.
- No hay validación de que un `page_id` no se registre más de una vez.

### Marcas con páginas distintas
- No hay relación entre `channels` y `brands`. Un channel se asocia a un `user_id`, no a una marca. No se puede diferenciar qué marca atiende qué canal.

### Onboarding / Configuración
- No existe. Todo es manual en la base de datos.

### Rate limiting de Meta
- **No se maneja.** Si Meta devuelve un 429, el `meta_graph.send_text_message()` lanza `MetaSendError` sin retry. El error se loguea y se pierde.

### Media / Attachments
- **No se persisten.** El webhook ignora mensajes sin `message.text`. Fotos, videos, stickers, audios y compartidos llegan como entradas sin `text` y se descartan silenciosamente.

### Stories / Reels / Comentarios
- **Solo DMs.** El webhook schema solo modela `messaging[]`. No hay soporte para `changes[]` (comentarios, stories mentions, etc.).

### Errores de fondo
- Si el background task de AI reply falla, se loguea la excepción pero no hay retry, dead letter queue, ni notificación. El cliente simplemente no recibe respuesta.

### Conversaciones sin cierre
- No hay flujo para cerrar/archivar conversaciones. El filtro en `_get_or_create_conversation` busca `status="open"`, pero nunca se cambia a otro valor. Todas las conversaciones quedan abiertas indefinidamente.

### `ai_suggestion` sin uso
- La columna `messages.ai_suggestion` existe en el modelo pero ningún servicio la escribe. Parece un vestigio de un modo "sugerencia al agente" que no se implementó.

---

## 9. UI / FRONTEND

**No hay frontend en este repositorio.** El workspace solo contiene el backend (FastAPI). No existen archivos `src/pages/`, `src/components/`, ni nada en JavaScript/TypeScript.

El frontend, si existe, vive en otro repositorio. Desde el backend, las pistas son:
- `ALLOWED_ORIGINS` incluye `localhost:5173` (Vite) y `localhost:3000` — sugiere un frontend en React/Vue con Vite.
- Los endpoints de conversations y messages no tienen auth, lo que sugiere que si hay un UI, es posible que use acceso directo sin token.
- No hay WebSocket implementado — si hay un inbox en el frontend, usaría polling o Supabase Realtime directamente.

---

## 10. ONBOARDING DEL USUARIO

### Estado actual: no hay onboarding

- **No hay flujo para que un usuario conecte su página.** Ni OAuth, ni UI, ni endpoint.
- Para conectar una página hoy, un desarrollador tiene que:
  1. Obtener un page access token manualmente (via Graph API Explorer o Facebook Login flow externo).
  2. Insertar un registro en la tabla `channels` con `user_id`, `page_id`, `access_token`, y opcionalmente `platform`.
  3. Configurar la URL del webhook manualmente en el panel de Meta Developers apuntando a `/api/v1/webhook/meta`.
  4. Suscribir la página al webhook usando la Graph API: `POST /{page_id}/subscribed_apps`.
- Los page access tokens en `.env` (`META_PAGE_ACCESS_TOKEN_1`, `_2`) sugieren que esto se hizo manualmente para 1-2 páginas de prueba.
- No hay forma de que un usuario final lo haga por sí mismo.

### Almacenamiento de tokens

- Los page access tokens se guardan en `channels.access_token` como texto plano en la DB.
- No están encriptados.
- No hay proceso de refresh.

---

## 11. HALLAZGOS INESPERADOS

### A. `META_PAGE_ACCESS_TOKEN_1` y `_2` en `.env` pero no en Settings
Los tokens están en el archivo `.env` pero la clase `Settings` no los define. Son valores residuales que no se cargan en la aplicación. Probablemente fueron usados durante el desarrollo inicial y luego se movió a la tabla `channels`.

### B. Bug de tipo en `process_incoming_message`
La firma de tipo de retorno dice `tuple[uuid.UUID, str]` pero en realidad retorna `tuple[uuid.UUID, str, str]` (incluye `mode`). El caller en `webhook.py` desestructura correctamente 3 valores. Es solo una anotación incorrecta.

### C. Endpoints de mensajes sin auth + TODO explícito
Hay comentarios `TODO` reconociendo que los endpoints de `/messages/` y `/conversations/` no tienen autenticación. El comentario en `messages.py` dice textualmente: _"auth strategy needs review — these endpoints are called internally by the Meta webhook flow (background tasks), not from the SPA frontend."_ Esto confirma que los endpoints están abiertos intencionalmente como workaround.

### D. Columna `phone_number_id` en channels
La tabla `channels` tiene `phone_number_id` (para WhatsApp Business API), pero no hay código que lo use. Es preparación para WhatsApp que nunca se implementó.

### E. `sender` como texto libre
Los valores de `messages.sender` (`"customer"`, `"ai"`, `"agent"`) no están restringidos por un enum, CHECK constraint, ni validación. Cualquier string podría insertarse.

### F. Sin índices en campos de búsqueda
- No hay índice en `channels.page_id` (se busca en cada webhook).
- No hay índice en `contacts(user_id, platform, platform_user_id)` (se busca en cada webhook).
- No hay índice en `conversations(contact_id, channel_id, status)` (se busca en cada webhook).
- Estos podrían existir a nivel de Supabase/Postgres directamente, pero no están definidos en los modelos SQLAlchemy.

### G. `lazy="selectin"` en relationships de Conversation
Los relationships `contact` y `channel` en `Conversation` usan `lazy="selectin"`, lo que significa que al cargar una conversación se emiten automáticamente queries adicionales. Esto es intencional y funcional, pero puede ser costoso si se cargan muchas conversaciones a la vez.

### H. Tests mínimos
Solo hay 4 tests para todo el módulo de messaging (2 de webhook, 2 de messages). Todos son tests negativos/de validación. No hay tests de happy path end-to-end, ni mocking de Meta API, ni tests del flujo completo webhook → AI → send.

### I. Background task usa nueva sesión de DB
La función `_process_ai_reply` en `webhook.py` crea una nueva sesión de DB via `async_session_factory()` en lugar de usar la sesión del request. Esto es correcto (el request ya terminó), pero significa que si la creación de la sesión falla, no hay retry.

### J. Secrets expuestos en `.env`
El archivo `.env` contiene secrets reales (API keys, tokens, private keys de GCP). Esto es habitual en desarrollo local pero debe asegurarse que `.env` esté en `.gitignore`.
