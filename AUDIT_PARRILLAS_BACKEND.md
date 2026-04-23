# 🛠️ Auditoría Backend — Flujo de Parrillas (NexusAI / Mavity)

**Fecha:** 2025-04-22  
**Alcance:** Backend only — FastAPI + Supabase + AI Providers  
**Autor:** GitHub Copilot (Claude Opus 4.6)

---

## 1. Mapa de Endpoints

### 1.1 Brand Agent (Brief Estratégico)

| Método | Path | Auth | Descripción | Input | Output | Services |
|--------|------|------|-------------|-------|--------|----------|
| POST | `/api/v1/agent/chat` | ✅ JWT | Envia mensaje al Brand Strategy Agent. Maneja interview conversacional y trigger de generación de pitch deck | `AgentChatRequest` — session_id, message, history[], logo_url, uploaded_images[] | `AgentChatResponse` — reply, presentation[], status, extracted_config, meta, creative_dna | `brand_agent.chat()` → `creative_director` → `slide_generator` → `slide_builder_v2` → `slide_postprocess` |
| POST | `/api/v1/agent/upload` | ✅ JWT | Sube logo/imagen a Supabase Storage (brand-assets bucket) | `UploadFile` + query: session_id, tag (general/logo/product_image) | `FileUploadResponse` — url, filename | `supabase_client.get_client()` (storage directo) |
| POST | `/api/v1/agent/search-images` | ❌ sin auth | Busca imágenes stock (Unsplash/Pexels) | `ImageSearchRequest` — query, count, orientation | `ImageSearchResponse` — results[] (url, thumb, alt, credit) | `image_search_service.search_images()` |
| DELETE | `/api/v1/agent/session/{session_id}` | ❌ sin auth | Limpia sesión de chat del agente (in-memory) | path param: session_id | `{status: "cleared"}` | Directo (dict pop) |

### 1.2 Posts (Generación de Parrilla)

| Método | Path | Auth | Descripción | Input | Output | Services |
|--------|------|------|-------------|-------|--------|----------|
| POST | `/api/v1/posts/render` | ❌ sin auth | Genera 1 post: Vertex AI → Nova Pro HTML → Playwright PNG | `RenderPostRequest` — format, brand, copy, image_prompt, style_description | `RenderPostResponse` — rendered_post (data URL), html_preview | `vertex_imagen`, `template_generator`, `template_renderer` |
| POST | `/api/v1/posts/render-batch-legacy` | ❌ sin auth | Render batch secuencial (caller provee copy + prompts) | `BatchRenderRequest` — brand, posts[] | `BatchRenderResponse` — results[] | Mismo pipeline que render |
| POST | `/api/v1/posts/render-batch` | ❌ sin auth | Pipeline inteligente: 1 LLM call → N posts con Flux/Vertex | `SmartBatchRenderRequest` — brand, campaign, product_images[], posts_config[], language, etc. | `SmartBatchRenderResponse` — results[] | `content_generator`, `flux_kontext`, `nano_banana`, `vertex_imagen`, `template_generator`, `template_renderer` |
| POST | `/api/v1/posts/generate` | ✅ JWT | **Generación async job-based**. Retorna job_id inmediatamente, genera en background | `SmartBatchRenderRequest` + draft_id | `GenerateResponse` — job_id, total_posts, status | `supabase_client` (jobs/posts), `content_generator`, `flux_kontext`, `nano_banana` |
| GET | `/api/v1/posts/job/{job_id}` | ✅ JWT | Poll del estado de un job de generación | path: job_id | `JobStatusResponse` — job{}, posts[] | `supabase_client.get_job_status()` |
| POST | `/api/v1/posts/{post_id}/video` | ✅ JWT | Inicia generación de video (Kling via fal.ai) | `VideoGenerateRequest` (duration, aspect_ratio) | `VideoGenerateResponse` — post_id, video_status | `video_generator`, `supabase_client` |
| GET | `/api/v1/posts/{post_id}/video/status` | ✅ JWT | Poll del estado de video | path: post_id | `VideoStatusResponse` — video_status, video_url, motion_prompt | `supabase_client.get_post()` |
| POST | `/api/v1/posts/{post_id}/edit-chat` | ✅ JWT | Edición iterativa por chat. Nova Pro Vision analiza y decide qué regenerar | `EditChatRequest` — user_message o quick_action | `EditChatResponse` — ai_response, change_scope, version_id, status | `edit_director`, `post_regenerator`, `supabase_client` |
| GET | `/api/v1/posts/{post_id}/edit-chat` | ✅ JWT | Historial de chat de edición | path: post_id | `EditChatHistoryResponse` — messages[] | `supabase_client.get_edit_chat_history()` |
| GET | `/api/v1/posts/{post_id}/versions` | ✅ JWT | Todas las versiones de un post | path: post_id | `PostVersionsResponse` — versions[] | `supabase_client.get_post_versions()` |
| POST | `/api/v1/posts/{post_id}/versions/{version_id}/restore` | ✅ JWT | Restaura versión específica de un post | path: post_id, version_id | `RestoreVersionResponse` | `supabase_client.restore_post_version()` |

### 1.3 Brand Analysis

| Método | Path | Auth | Descripción | Input | Output | Services |
|--------|------|------|-------------|-------|--------|----------|
| POST | `/api/v1/brand/analyze` | ✅ JWT | Extrae paleta de colores de logo (ColorThief local) | `AnalyzeBrandRequest` — logo_b64 | `AnalyzeBrandResponse` — primary_color, palette[], suggested_fonts[] | `brand_analyzer` |
| POST | `/api/v1/brand/analyze-vision` | ✅ JWT | Análisis full: colores + AI vision (Nova Pro). Modo efímero o persistente | `BrandVisionRequest` — logo_b64, brand_id? | `BrandVisionResponse` — analysis{}, logo_url, persisted | `brand_analyzer`, `vision_analyzer`, `storage_helper` |

### 1.4 Product

| Método | Path | Auth | Descripción | Input | Output | Services |
|--------|------|------|-------------|-------|--------|----------|
| POST | `/api/v1/product/analyze` | ✅ JWT | Analiza producto con Nova Pro vision. Efímero o persistente | `ProductAnalyzeRequest` — product_b64, brand_id?, persist?, product_name? | dict con analysis, persisted, product_id? | `vision_analyzer`, `storage_helper` |
| GET | `/api/v1/product/brands/{brand_id}/products` | ✅ JWT | Lista productos de una marca | path: brand_id | list[dict] | `supabase_client` directo |
| PATCH | `/api/v1/product/{product_id}` | ✅ JWT | Actualiza nombre/orden/is_primary | `UpdateProductRequest` | dict | `supabase_client` directo |
| DELETE | `/api/v1/product/{product_id}` | ✅ JWT | Elimina producto + archivo en storage | path: product_id | 204 | `storage_helper.delete_storage_object()` |

### 1.5 Brands CRUD

| Método | Path | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/api/v1/brands` | ✅ JWT | Lista marcas de la agencia |
| GET | `/api/v1/brands/{brand_id}` | ✅ JWT | Obtiene marca por ID |
| POST | `/api/v1/brands` | ✅ JWT | Crea nueva marca |
| PATCH | `/api/v1/brands/{brand_id}` | ✅ JWT | Actualiza marca |
| DELETE | `/api/v1/brands/{brand_id}` | ✅ JWT | Elimina marca |

### 1.6 Drafts (Parrilla Drafts)

| Método | Path | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/api/v1/drafts` | ✅ JWT | Crea nuevo draft de parrilla |
| GET | `/api/v1/drafts` | ✅ JWT | Lista drafts (filtro por status y brand_id) |
| GET | `/api/v1/drafts/{draft_id}` | ✅ JWT | Obtiene draft |
| PATCH | `/api/v1/drafts/{draft_id}` | ✅ JWT | Auto-save: chat_messages, config, selected_product_ids, title, last_step, brand_id |
| DELETE | `/api/v1/drafts/{draft_id}` | ✅ JWT | Elimina draft |

### 1.7 Chat (Nano Banano — Post Chat)

| Método | Path | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/api/v1/chat` | ✅ JWT | Chat con Nano Banano (Nova Pro) para refinar campaña pre-generación. Prompt de 4+ preguntas antes de generar. | 

### 1.8 Messaging (Meta/Facebook)

| Método | Path | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/api/v1/webhook/meta` | ❌ | Verificación webhook Meta |
| POST | `/api/v1/webhook/meta` | ❌ | Recibe mensajes entrantes Meta. Background task genera AI reply |
| POST | `/api/v1/messages/ai-reply` | ❌ sin auth | Genera reply AI y envía vía Meta Graph API |
| POST | `/api/v1/messages/send` | ❌ sin auth | Envía mensaje manual del agente |
| PATCH | `/api/v1/conversations/{id}/mode` | ❌ sin auth | Toggle modo ai/manual en conversaciones |

### 1.9 Otros

| Método | Path | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/api/v1/user/me` | ✅ JWT | Info del usuario autenticado |
| GET | `/api/v1/agency/me` | ✅ JWT | Agencia del usuario |
| GET | `/api/v1/templates` | ❌ | Lista templates HTML estáticos disponibles |
| GET | `/api/v1/temp-images/{filename}` | ❌ | Sirve imágenes temporales de Flux |
| GET | `/health` | ❌ | Health check |
| GET | `/uploads/{path}` | ❌ | Static files (uploads locales /tmp/uploads) |
| POST | `/api/v1/images/generate` | ❌ sin auth | Genera imagen con Vertex AI Imagen 3 + logo overlay |

---

## 2. Mapa de Services

### 2.1 `brand_agent.py` — Brand Strategy Agent
- **Función principal:** `chat()` — procesa mensajes del usuario en entrevista conversacional, detecta trigger `generate_presentation`, y ejecuta pipeline de 3 fases.
- **Modelo IA (Pass 1):** Bedrock `bedrock_model_id` (default: Claude 3.5 Sonnet) con fallback a Gemini.
- **Pipeline:** Detect JSON → `creative_director` → `slide_generator` → `slide_builder_v2` → `slide_postprocess`.
- **Errores / Fallbacks:** Try/except en cada fase. Si el pipeline falla, responde con warning al usuario "intenta de nuevo diciendo 'genera'".
- **Nota:** Sessions almacenadas **in-memory** (`_sessions` dict). Se pierden en restart.

### 2.2 `creative_director.py` — Phase 1 (Planner)
- **Función principal:** `generate_creative_vision()` — decide complejidad (6-15 slides), mood kit (BOLD/EDITORIAL/PLAYFUL/MINIMAL), creative DNA, y deck_plan.
- **Modelo:** `bedrock.invoke_with_fallback()` (chain: zai.glm-5 → zai.glm-4.7 → amazon.nova-pro-v1:0), fallback a Gemini si toda la chain falla.
- **Errores:** Parse fallback robusto — intenta code block, luego raw JSON, luego plan default de 6 slides.

### 2.3 `slide_generator.py` — Phase 2 (Workers paralelos)
- **Función principal:** `generate_all_slides()` — lanza N workers en paralelo con `asyncio.gather` + Semaphore(5).
- **Modelo:** `bedrock.invoke_with_fallback()` por slide.
- **Timeout:** 30 segundos por slide (`SLIDE_GENERATION_TIMEOUT`).
- **Errores:** Cada slide tiene fallback individual (`_fallback_slide`). Si uno falla, el deck continúa con contenido fallback.

### 2.4 `slide_builder_v2.py` — Template dispatch
- **Función:** `build_presentation()` — convierte slide content en elementos visuales usando mood_kits (layouts predefinidos).
- **No usa IA.** Puro Python con layout algorithms.

### 2.5 `slide_postprocess.py` — Phase 3 (Validación)
- **Función:** `postprocess_presentation()` — WCAG contrast fix, text overlap 3-pass, logo injection, DNA compliance, z-index compaction.
- **No usa IA.** Puro Python.

### 2.6 `content_generator.py` — Generador de Copy para Posts
- **Función principal:** `generate_post_content()` — usa Nova Pro para generar headline, body, cta, image_prompt, style_description para N posts en una sola llamada.
- **Modelo:** `template_model_id` (default: `amazon.nova-pro-v1:0`) invocado directo con `invoke_model`.
- **Función auxiliar:** `enrich_context_from_supabase()` — enriquece contexto desde brands + brand_products de Supabase.
- **Errores:** Parse JSON con fallback a buscar array dentro del texto.

### 2.7 `edit_director.py` — Analizador de ediciones
- **Función:** `analyze_edit_request()` — usa Nova Pro **VISION** (multimodal) para analizar imagen actual + feedback del usuario y clasificar en: `copy_only`, `text_overlay`, `logo_overlay`, `base_image`, `full`.
- **Modelo:** `amazon.nova-pro-v1:0` (hardcoded, no configurable).
- **Quick actions:** 8 presets (more_vibrant, different_angle, more_minimalist, etc.).
- **Errores:** Parse JSON con fallback. Si change_scope inválido, default a `base_image`.

### 2.8 `post_regenerator.py` — Ejecutor de regeneraciones
- **Función:** `regenerate_post()` — 5 modos de regeneración según el change_scope del edit_director.
- **servicios usados:** `nano_banana`, `flux_kontext`, `supabase_client` (versiones, storage).
- **No usa IA directamente** — usa Flux/Nano Banana para imágenes.

### 2.9 `video_generator.py` — Video generation (Kling)
- **Funciones:** `generate_motion_prompt()` (Nova Pro Vision) → `generate_video()` (Kling via fal.ai queue API).
- **Modelo:** `amazon.nova-pro-v1:0` para motion prompt, Kling v2.5 turbo/pro para video.
- **Timeout:** Pool de hasta 90 intentos × 3s = ~4.5 min max.

### 2.10 `vision_analyzer.py` — análisis multimodal
- **Funciones:** `analyze_logo()`, `analyze_product()` — Nova Pro vision para extraer metadatos de logos y productos.
- **Modelo:** `amazon.nova-pro-v1:0` (hardcoded).

### 2.11 `brand_analyzer.py` — Extracción de paleta
- **Función:** `analyze_brand_from_logo()` — usa ColorThief (Python, local) para extraer paleta de colores.
- **No usa IA.** Puro Python + ColorThief + PIL.

### 2.12 `template_generator.py` — HTML template generation
- **Función:** `generate_post_template()` — Nova Pro genera HTML/CSS inline para posts.
- **Modelo:** `template_model_id` (default: `amazon.nova-pro-v1:0`).

### 2.13 `template_renderer.py` — HTML → PNG
- **Función:** `render_html_to_png()` — Playwright headless Chromium.
- **No usa IA.**

### 2.14 `nano_banana.py` — Logo/text overlay
- **Función:** `enhance_post_image()` — agrega logo y/o texto a imágenes vía Nano Banana 2 Edit (fal.ai).
- **API:** `fal.run/fal-ai/nano-banana-2/edit`.

### 2.15 `flux_kontext.py` — Image-to-image generation
- **Función:** `generate_image_with_reference()` — Flux Kontext Pro para product placement.
- **API:** `fal.run/fal-ai/flux-pro/kontext` y `fal.run/fal-ai/flux-2-pro/edit`.

### 2.16 `language_detector.py` — Detección de idioma
- **Función:** `detect_language()` — una llamada mínima a Nova Pro (5 tokens) para clasificar es/en.

### 2.17 `image_search_service.py` — Stock images
- **Función:** `search_images()` — Unsplash con fallback a Pexels.

### 2.18 `ai_service.py` — Router de AI providers
- **Función:** `generate_response()` — router que despacha a Bedrock o Gemini según `settings.ai_provider`.

### 2.19 `message_service.py` / `webhook_service.py` — Messaging Meta
- Manejo de mensajes entrantes/salientes de Facebook/Instagram via Meta Graph API.
- Usa SQLAlchemy con DB local (conversations, messages, contacts, channels).

### 2.20 `mockup_generator.py` — Phone mockup layouts
- **Función:** `build_phone_mockup()` — genera elementos de slide con frame de teléfono para apps digitales.
- **No usa IA.** Puro layout.

### 2.21 `storage_helper.py` — Supabase Storage wrappers
- Upload/delete de logos y product images al bucket `brand-assets`.

### 2.22 `image_storage.py` — fal.ai data URL converter
- Convierte base64 a data URL para consumo directo de fal.ai. No sube a ningún servidor.

### 2.23 `supabase_client.py` — Data access layer
- CRUD completo para `generation_jobs`, `generated_posts`, `post_versions`, `post_edit_chat`.
- Upload de imágenes/videos al bucket `post-images`.
- **NO es async nativo** — usa el SDK sync de Supabase pero las funciones están declaradas como `async`.

---

## 3. Providers de IA

### 3.1 `providers/bedrock.py` — AWS Bedrock (texto)
- **API:** AWS Bedrock Converse API.
- **Modelos expuestos:**
  - **Primary chat:** `bedrock_model_id` (default: `anthropic.claude-3-5-sonnet-20241022-v2:0`)
  - **Template/content gen:** `template_model_id` (default: `amazon.nova-pro-v1:0`)
  - **Agent vision:** `agent_vision_model` (default: `us.amazon.nova-pro-v1:0`)
  - **Agent slides:** `agent_slide_model` (default: `zai.glm-5`)
  - **Agent director:** `agent_director_model` (default: `zai.glm-5`)
  - **Fallback chain:** `zai.glm-5` → `zai.glm-4.7` → `us.amazon.nova-pro-v1:0`
- **Concurrencia:** Semaphore(5) (`MAX_CONCURRENT_INVOKES`).
- **Retry:** Exponential backoff (1s, 2s, 4s) para ThrottlingException, ServiceUnavailableException, ModelTimeoutException. Max 3 retries.
- **Funciones:** `invoke()`, `invoke_bounded()` (con semaphore), `invoke_with_fallback()` (chain), `generate_response()` (backward-compat).
- **Costos:** GLM-5 (más barato, rate limits altos), Nova Pro (~$0.0008/1K input, ~$0.0032/1K output), Claude 3.5 Sonnet (~$0.003/1K input, ~$0.015/1K output).

### 3.2 `providers/gemini.py` — Google Gemini (texto, fallback)
- **API:** REST `generativelanguage.googleapis.com/v1beta`.
- **Modelo:** `gemini-2.0-flash` (default).
- **Auth:** API key (`gemini_api_key`).
- **Uso:** Fallback de Bedrock para la charla del brand agent y el creative director.
- **Timeout:** 120s.
- **Sin retry propio** — si falla, propaga error.

### 3.3 `providers/vertex_imagen.py` — Vertex AI Imagen 3 (imágenes)
- **API:** REST Vertex AI `aiplatform.googleapis.com`.
- **Modelo:** `imagen-3.0-generate-002`.
- **Auth:** GCP Service Account JSON → access token con refresh automático.
- **Output:** Base64 PNG.
- **Uso:** Fallback de Flux cuando no hay product images (text-to-image puro).
- **Costo:** ~$0.04 por imagen generada.
- **Timeout:** 120s.

### 3.4 `services/flux_kontext.py` — Flux Kontext Pro (image-to-image, via fal.ai)
- **API:** `fal.run/fal-ai/flux-pro/kontext` y `fal.run/fal-ai/flux-2-pro/edit`.
- **Auth:** fal.ai API key.
- **Uso:** Pipeline principal de generación de imágenes cuando hay product photos. El producto real se coloca en escenas generadas.
- **Costo:** ~$0.05-0.10 por imagen (fal.ai pricing).
- **Timeout:** 300s (largo por queue).

### 3.5 `services/nano_banana.py` — Nano Banana 2 Edit (logo+text overlay, via fal.ai)
- **API:** `fal.run/fal-ai/nano-banana-2/edit`.
- **Auth:** fal.ai API key.
- **Uso:** Post-processing — integra logo y/o texto sobre imágenes Flux.
- **Costo:** ~$0.03-0.05 por imagen.
- **Timeout:** 120s.

### 3.6 `services/video_generator.py` — Kling v2.5 (video, via fal.ai)
- **API:** `queue.fal.run/fal-ai/kling-video/v2.5-turbo/pro/image-to-video`.
- **Auth:** fal.ai API key.
- **Uso:** Image-to-video desde posts generados. Nova Pro genera motion prompt, Kling genera 5-10s de video.
- **Costo:** ~$0.10-0.30 por video (5s).
- **Timeout:** Polling loop: 90 polls × 3s = ~4.5 min.

### 3.7 `providers/pinecone.py` — Pinecone (stub)
- **Estado:** Solo placeholder con `NotImplementedError`. No conectado.

### 3.8 `providers/meta_graph.py` — Meta Graph API (messaging)
- **API:** `graph.facebook.com/v21.0/me/messages`.
- **Uso:** Envío de mensajes a customers vía Facebook Messenger.

### 3.9 Image Search (Unsplash + Pexels)
- **APIs:** `api.unsplash.com/search/photos` + `api.pexels.com/v1/search`.
- **Auth:** API keys separadas.
- **Uso:** Fotos stock para slides del pitch deck.
- **Fallback:** Unsplash → Pexels.
- **Rate limits:** Unsplash 50 req/hr (free), Pexels 200 req/hr.

---

## 4. Schema de DB

### 4.1 Tablas en SQLAlchemy (ORM local — messaging)

**`channels`**
| Column | Type | Nullable |
|--------|------|----------|
| id | UUID PK | no |
| user_id | UUID | no |
| platform | text | sí |
| page_id | text | sí |
| access_token | text | sí |
| phone_number_id | text | sí |
| created_at | timestamp | sí (default now) |

**`contacts`**
| Column | Type | Nullable |
|--------|------|----------|
| id | UUID PK | no |
| user_id | UUID | no |
| platform | text | sí |
| platform_user_id | text | sí |
| name | text | sí |
| created_at | timestamp | sí (default now) |

**`conversations`**
| Column | Type | Nullable |
|--------|------|----------|
| id | UUID PK | no |
| user_id | UUID | no |
| contact_id | UUID FK→contacts | no |
| channel_id | UUID FK→channels | no |
| status | text | sí (default "open") |
| mode | text | sí |
| last_message_at | timestamp | sí |

**`messages`**
| Column | Type | Nullable |
|--------|------|----------|
| id | UUID PK | no |
| conversation_id | UUID FK→conversations | no |
| sender | text | sí |
| content | text | sí |
| ai_suggestion | text | sí |
| sent_at | timestamp | sí (default now) |

### 4.2 Tablas en Supabase (acceso directo via SDK, sin ORM)

Estas tablas se infieren del uso en código — no hay migraciones SQL locales que las definan. Los campos usados son:

**`agencies`** (inferido de auth middleware)
- id, name

**`agency_members`** (inferido de auth middleware)
- user_id, agency_id, role → join con agencies(id, name)

**`brands`**
- id, agency_id, name, logo_url, vision_analysis (JSONB), detected_at
- primary_color, secondary_color, accent_color, contrast_color, font_family
- created_at

**`brand_products`**
- id, brand_id, name, image_url, storage_path, vision_analysis (JSONB)
- analyzed_at, display_order, is_primary

**`parrilla_drafts`**
- id, agency_id, brand_id, user_id, title
- status ("draft" → "generating" → "generated")
- chat_messages (JSONB array), config (JSONB)
- selected_product_ids (JSONB array de UUIDs)
- last_step, updated_at

**`generation_jobs`**
- id, total_posts, completed_posts, brand_name, campaign_description
- status ("processing" → "completed" | "failed")
- error_message, language, agency_id, draft_id, config (JSONB)

**`generated_posts`**
- id, job_id, index, platform, format
- status ("generating" → "success" | "error"), error_message
- headline, body, cta, image_prompt
- rendered_image_url, base_image_url
- video_url, video_status, video_error, motion_prompt
- current_version_number, edit_status ("idle" | "regenerating" | "failed")

**`post_versions`**
- id, post_id, version_number, is_current (bool)
- headline, body, cta, image_prompt
- rendered_image_url, base_image_url
- user_message, ai_response, change_scope
- created_at

**`post_edit_chat`**
- id, post_id, role, content, version_id, created_at

### 4.3 RLS Policies, Foreign Keys, Triggers

**No hay acceso al schema de Supabase desde el código.** Las policies RLS se manejan del lado de Supabase. El código usa `supabase_service_role_key` (bypass RLS) para la mayoría de operaciones en `supabase_client.py`, y `user.jwt_token` (con RLS) para las consultas en `auth.py` (e.g., `agency_members`).

**Foreign Keys inferidas:**
- `brand_products.brand_id → brands.id`
- `parrilla_drafts.agency_id → agencies.id`
- `parrilla_drafts.brand_id → brands.id`
- `generation_jobs.agency_id → agencies.id`
- `generation_jobs.draft_id → parrilla_drafts.id`
- `generated_posts.job_id → generation_jobs.id`
- `post_versions.post_id → generated_posts.id`
- `post_edit_chat.post_id → generated_posts.id`

**Triggers:** No hay triggers definidos en el código. Supabase puede tener triggers server-side no visibles aquí (e.g., `updated_at` automático).

---

## 5. Estado del Flujo de Generación de Posts

### 5.1 ¿Existe un endpoint que genera posts a partir de brief + config?

**SÍ.** `POST /api/v1/posts/generate` es el endpoint principal. Acepta `SmartBatchRenderRequest` que incluye brand, campaign, product_images, y posts_config. Retorna un `job_id` inmediatamente y genera en background vía `BackgroundTasks`.

### 5.2 ¿Usa paralelización?

**NO para posts.** A diferencia del agente de briefs (que usa `asyncio.gather` + Semaphore(5) para slides), la generación de posts es **secuencial** — un for loop que procesa post por post en `_generate_posts_background()`. Cada post completado se guarda inmediatamente a Supabase, permitiendo al frontend mostrar progreso incremental.

### 5.3 Columnas de `generation_jobs` usadas hoy

| Columna | Uso |
|---------|-----|
| id | PK, UUID auto |
| total_posts | Número de posts solicitados |
| completed_posts | Counter incremental |
| brand_name | Para contexto |
| campaign_description | Para contexto |
| status | "processing" → "completed" / "failed" |
| error_message | Si falla |
| language | "es" o "en" |
| agency_id | Multi-tenancy |
| draft_id | FK a parrilla_drafts (opcional) |
| config | JSONB con config del draft |

### 5.4 Columnas de `generated_posts` usadas hoy

Todas las listadas en § 4.2 están activamente en uso. El flujo completo es:
1. Placeholder con status "generating"
2. Éxito: headline, body, cta, image_prompt, rendered_image_url, status "success"
3. O error: error_message, status "error"
4. Video: video_url, video_status, motion_prompt
5. Edición: edit_status, current_version_number, base_image_url

### 5.5 ¿Qué IA genera copy?

**Amazon Nova Pro** (`amazon.nova-pro-v1:0`) via `content_generator._call_nova()` — invocación directa con `invoke_model` (no usa Converse API). Una sola llamada genera copy para todos los posts del batch.

### 5.6 ¿Qué IA genera imágenes?

- **Con product photos:** Flux Kontext Pro (image-to-image) → opcionalmente Nano Banana 2 Edit (logo/text overlay).
- **Sin product photos:** Vertex AI Imagen 3 (text-to-image fallback).
- La decisión es automática según si `product_images` está en el payload.

### 5.7 ¿Video?

**Kling v2.5 turbo/pro** via fal.ai queue API. Nova Pro genera motion prompt con vision, luego Kling genera video. Es on-demand por post (no batch).

### 5.8 ¿Hay workers para paralelizar?

**No para posts.** Los posts se generan secuencialmente. Solo la Fase 2 del agente de briefs usa workers paralelos.

### 5.9 ¿Retry / backoff?

- **Bedrock:** Sí — 3 retries con exponential backoff (1s, 2s, 4s) para throttling/timeout.
- **Flux/Nano Banana/Kling:** No — si falla, el post individual se marca como error pero el job continúa.
- **Vertex AI Imagen:** No retry.
- **Job-level:** Si todo el job falla (excepción en el outer try), se marca como "failed".

### 5.10 ¿Timeout?

- `render` endpoint: 90s (`asyncio.wait_for`).
- `render-batch`: 90s por item.
- Content generation LLM call: 60s.
- Background worker: Sin timeout global — cada servicio externo tiene su propio timeout (Flux: 300s, Kling: polling ~4.5min).

---

## 6. Integración con Servicios Externos

### 6.1 Supabase (Postgres + Storage + Auth)
- **Variables:** `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `DATABASE_URL`
- **Cliente Postgres (ORM):** `app/db/session.py` — SQLAlchemy async con SSL.
- **Cliente Supabase SDK:** `app/services/supabase_client.py` — `supabase.create_client()` con service role key.
- **Storage buckets:** `brand-assets` (logos, product images), `post-images` (rendered posts, videos).
- **Auth:** JWKS endpoint para validar JWTs ES256.
- **Health check:** No hay health check a Supabase. Si la DB está caída, las queries fallan con error 500 genérico.

### 6.2 AWS Bedrock
- **Variables:** `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`
- **Cliente:** `app/providers/bedrock.py` + `app/services/template_generator.py` (segundo cliente `lru_cache`).
- **Health check:** No. Fallback chain funciona como pseudo-health-check.

### 6.3 fal.ai (Flux, Nano Banana, Kling)
- **Variables:** `FAL_KEY`
- **Clientes:** `app/services/flux_kontext.py`, `app/services/nano_banana.py`, `app/services/video_generator.py`.
- **Health check:** No. Si fal.ai está caído, el post falla con error genérico.

### 6.4 Google Cloud (Vertex AI Imagen + Gemini)
- **Variables:** `GCP_PROJECT_ID`, `GCP_LOCATION`, `GCP_SERVICE_ACCOUNT_JSON`, `GEMINI_API_KEY`
- **Clientes:** `app/providers/vertex_imagen.py`, `app/providers/gemini.py`.
- **Health check:** No.

### 6.5 Unsplash + Pexels
- **Variables:** `UNSPLASH_ACCESS_KEY`, `PEXELS_API_KEY`
- **Cliente:** `app/services/image_search_service.py`.
- **Fallback:** Unsplash falla → intenta Pexels.

### 6.6 Meta Graph API
- **Variables:** `META_VERIFY_TOKEN`, `META_APP_SECRET`
- **Cliente:** `app/providers/meta_graph.py`.
- **Auth:** page access token almacenado en tabla `channels`.

---

## 7. Middleware y Auth

### 7.1 JWT Verification
- **Implementación:** `app/middleware/auth.py` → `get_current_user()` dependency.
- **Dual-mode:**
  - **ES256 vía JWKS** (preferido): descarga signing key de `{supabase_url}/auth/v1/.well-known/jwks.json` con cache de 1 hora.
  - **HS256 legacy:** Si el header del JWT indica HS256, valida con `SUPABASE_JWT_SECRET`.
- **Multi-tenancy:** `get_user_agency()` resuelve `agency_members` con el JWT del usuario (respeta RLS).
- **Audience:** Valida `aud: "authenticated"`.

### 7.2 Rate Limiting
**No hay rate limiting implementado.** Ni en middleware ni en endpoints individuales. Cualquier usuario autenticado puede hacer requests ilimitados.

### 7.3 CORS
```python
CORSMiddleware(
    allow_origins=["*"],      # ⚠️ Todos los orígenes
    allow_credentials=True,   # ⚠️ Cookies cross-origin permitidas
    allow_methods=["*"],
    allow_headers=["*"],
)
```
**Problema de seguridad:** `allow_origins=["*"]` con `allow_credentials=True` es inseguro en producción. Los navegadores ignoran `*` cuando credentials=True, pero la intención es mala. Debería restringirse a dominios específicos.

### 7.4 Error Handler
- `ErrorHandlerMiddleware` — catch-all que loguea traceback y retorna 500 genérico. No expone detalles internos al cliente.

---

## 8. Bugs / Deuda Técnica

### 8.1 Funciones de 100+ líneas

| Archivo | Función | Líneas aprox | Problema |
|---------|---------|-------------|----------|
| `posts.py` | `_generate_posts_background` | ~120 | Worker monolítico secuencial. Mezcla upload, generación, storage |
| `posts.py` | `smart_render_batch` | ~100 | Mismo lógica duplicada con `_generate_posts_background` |
| `brand_agent.py` | `chat()` | ~100 | Manejo del pipeline dentro del handler de chat |
| `chat.py` | `_build_system_prompt()` | ~90 | Prompt gigante hardcoded |
| `creative_director.py` | Prompt constante | ~100 | String constante, no una función, pero es masivo |

### 8.2 Código duplicado

| Dónde | Qué se duplica |
|-------|---------------|
| `providers/bedrock.py` vs `services/template_generator.py` | **Dos clientes Bedrock separados** (`_get_bedrock_client`) con la misma config, ambos `lru_cache`. |
| `posts.py` `smart_render_batch` vs `_generate_posts_background` | Lógica duplicada de Flux → Nano Banana → upload. El endpoint sync y el background worker tienen ~80% del mismo código. |
| `vision_analyzer.py`, `edit_director.py`, `video_generator.py` | Todos importan `_get_bedrock_client` de `template_generator.py` en vez de usar `providers/bedrock.py`. |
| `_parse_json_text()` / `_extract_json_block()` | JSON parsing repetido en 5+ archivos con variaciones sutiles. |
| `_strip_b64_prefix()` | Implementado independientemente en `vision_analyzer.py` y `storage_helper.py`. |

### 8.3 Error handling inconsistente

| Problema | Dónde |
|----------|-------|
| `except Exception` con `raise HTTPException` que expone `str(exc)` al cliente | `brand.py` L26, `chat.py` L133, `posts.py` varios lugares |
| `except Exception as exc: logger.error(...)` sin re-raise ni notificación | `_generate_posts_background` — si un post falla, solo se loguea |
| `supabase_client.py` funciones marcadas `async` pero ejecutan código sync | Toda la file — las operaciones de Supabase SDK son sync, el `async` es cosmético |

### 8.4 Logs que exponen info sensible

| Riesgo | Archivo | Status |
|--------|---------|--------|
| **gemini.py**: loguea `body=response.text` en error — puede contener API key en la URL si Gemini la refleja | `gemini.py` L39 | ⚠️ Riesgo bajo (body, no URL params) |
| **vertex_imagen.py**: loguea `body=response.text` en error | `vertex_imagen.py` L65 | ⚠️ Similar |
| **bedrock.py**: loguea `data=response` — podría incluir contenido del modelo | `bedrock.py` L93 | ⚠️ Riesgo bajo |
| **edit_director.py**: loguea `response=raw[:200]` — puede contener texto sensible del usuario | `edit_director.py` L152 | ⚠️ Riesgo medio |
| **No hay leak de Google API key actualmente** — Gemini API key se envía como query param, no se loguea directamente | | ✅ Verificado OK |

### 8.5 `except Exception` sin logging apropiado

| Archivo | Línea | Problema |
|---------|-------|---------|
| `template_renderer.py` | `stop_browser()` | `except Exception: pass` — silencia errores de cleanup |
| Múltiples `_parse_json_*` | Varios | try/except que silencian JSONDecodeError en primer intento |

### 8.6 Endpoints sin auth que deberían tenerla

| Endpoint | Riesgo |
|----------|--------|
| `POST /api/v1/posts/render` | ⚠️ Cualquiera puede generar posts (consume Vertex AI $) |
| `POST /api/v1/posts/render-batch-legacy` | ⚠️ Mismo — batch sin auth |
| `POST /api/v1/posts/render-batch` | ⚠️ Mismo — batch inteligente sin auth |
| `POST /api/v1/images/generate` | ⚠️ Genera imágenes con Vertex AI sin auth |
| `POST /api/v1/messages/ai-reply` | ⚠️ Genera AI reply sin auth |
| `POST /api/v1/messages/send` | ⚠️ Envía mensajes Meta sin auth |
| `PATCH /api/v1/conversations/{id}/mode` | ⚠️ Toggle de conversación sin auth |
| `POST /api/v1/agent/search-images` | ⚠️ Bajo riesgo (gratis) pero sin auth |
| `DELETE /api/v1/agent/session/{session_id}` | ⚠️ Cualquiera puede borrar sesiones |

### 8.7 N+1 Queries

No hay N+1 queries evidentes. La mayoría de las consultas son lookup simple por ID o filtro. El endpoint `GET /job/{job_id}` hace 2 queries (job + posts) lo cual es correcto.

### 8.8 Otros problemas

| Problema | Detalle |
|----------|---------|
| **Sessions in-memory** | `brand_agent.py::_sessions` es un dict global. Se pierde en restart, no escala horizontalmente, potencial memory leak con sesiones abandonadas |
| **Supabase SDK sync** | Todo `supabase_client.py` usa SDK sync dentro de funciones `async`. No bloquea el event loop solo porque no hay I/O pesado inline, pero `asyncio.to_thread()` sería más correcto |
| **No hay cleanup de temp_images** | `temp_images/` crece sin límite |
| **SSL: verify_mode = CERT_NONE** | `db/session.py` desactiva verificación SSL. Riesgo de MITM en producción |
| **CORS wildcard** | `allow_origins=["*"]` con `allow_credentials=True` |
| **No hay request size limits** | Aparte de la validación de 5MB en upload, no hay límite global |
| **Background tasks sin DLQ** | Si `_generate_posts_background` o `_generate_video_background` fallan, no hay retry automático ni dead letter queue |

---

## 9. Propuesta de Arquitectura para Completar Parrillas (Backend)

### Fase 1 — Flujo básico end-to-end (Complejidad: BAJA)

**Objetivo:** El usuario crea una parrilla con N posts y obtiene resultados.

**Lo que ya funciona:**
- `POST /drafts` — crear draft
- `PATCH /drafts/{id}` — auto-save config
- `POST /posts/generate` — generar posts async
- `GET /posts/job/{id}` — poll status
- `POST /posts/{id}/edit-chat` — editar posts
- `POST /posts/{id}/video` — generar video

**Lo que falta (minimal):**
1. **Endpoint `POST /api/v1/drafts/{draft_id}/generate`** — wrapper que toma un draft, lee su config + brand + productos, y llama internamente a la lógica de `generate`. Hoy el frontend tiene que armar el `SmartBatchRenderRequest` manualmente.
2. **Columnas nuevas en `parrilla_drafts`:** `generated_job_id` (FK a generation_jobs), `platform_config` (JSONB — plataformas + formatos), `pillar_config` (JSONB — pilares de contenido), `schedule` (JSONB — fechas).
3. **Endpoint `GET /api/v1/drafts/{draft_id}/posts`** — retorna todos los generated_posts del job vinculado al draft. Hoy hay que ir por job_id.

### Fase 2 — Paralelización de generación (Complejidad: MEDIA)

**Objetivo:** Generar N posts en paralelo como el agente de briefs.

**Cambios:**
1. **Refactor `_generate_posts_background()`** usando el patrón de `slide_generator.py`:
   ```
   - Semaphore(3) para Flux (evitar rate limit fal.ai)
   - asyncio.gather con per-post timeout (120s)
   - Fallback para post individual que falla
   ```
2. **Separar la generación en 3 fases (como el agente):**
   - **Fase 1: Content Director** — un solo LLM call generando copy para todos los posts (ya existe: `content_generator`).
   - **Fase 2: Image Workers** — N workers paralelos generando imágenes (Flux/Vertex).
   - **Fase 3: Post-process** — storage upload + versión + meta.
3. **Nuevo service: `post_pipeline.py`** — orquestador del pipeline que reuse la lógica dispersa en `posts.py`.

### Fase 3 — Cost control: imágenes al aprobar (Complejidad: MEDIA)

**Objetivo:** No gastar en Flux/Kling hasta que el usuario apruebe.

**Cambios:**
1. **Fase 1 solo genera copy** — headline, body, cta, image_prompt (texto). Sin llamar a Flux/Vertex.
2. **Nuevo `status` en `generated_posts`:** "copy_ready" → "image_generating" → "success".
3. **Endpoint `POST /api/v1/posts/{post_id}/approve`** — trigger la generación de imagen para un post aprobado. Background task.
4. **Endpoint `POST /api/v1/posts/job/{job_id}/approve-all`** — aprueba todos, genera imágenes en paralelo.
5. **Columna `approved_at`** en `generated_posts`.

**Impacto en costos:** Si el usuario descarta 5 de 10 posts sin aprobar, se ahorran ~$0.25-0.50 en Flux + $0.15-0.25 en Nano Banana.

### Fase 4 — Real-time updates vía SSE (Complejidad: MEDIA)

**Objetivo:** Evitar polling. El frontend recibe updates en real-time.

**Cambios:**
1. **Endpoint `GET /api/v1/posts/job/{job_id}/stream`** — SSE endpoint que emite eventos conforme cada post se completa.
2. **Implementación:** `asyncio.Queue` per job + `StreamingResponse` de FastAPI.
3. **Eventos:** `post_started`, `post_completed`, `post_failed`, `job_completed`.
4. **Fallback:** El polling con `GET /job/{id}` sigue funcionando para clientes que no soporten SSE.

### Fase 5 — Scheduling y publicación (Complejidad: ALTA)

**Objetivo:** Posts aprobados se publican automáticamente en la fecha programada.

**Cambios:**
1. **Tabla nueva: `scheduled_posts`** — post_id, platform, scheduled_at, published_at, status.
2. **Worker periódico** (APScheduler o Celery beat) que revisa posts pendientes cada minuto.
3. **Integración con Meta Graph API** para publicación — requiere permisos de publish_pages.
4. **Posible integración con Later/Buffer API** como alternativa a publicación directa.

### Fase 6 — Queue robusta para alta concurrencia (Complejidad: ALTA)

**Objetivo:** Múltiples usuarios generando al mismo tiempo.

**Cambios:**
1. **Migrar de `BackgroundTasks` a Celery/Redis** o **ARQ (async Redis queue)**.
2. **Retry automático** con backoff para tasks que fallan.
3. **Dead letter queue** para jobs que fallan 3+ veces.
4. **Dashboard de jobs** — endpoint admin para ver estado de queue.
5. **Priority queue** — jobs de agencies premium van primero.

---

## 10. Riesgos Técnicos

### 10.1 Rate Limits de Bedrock
- **GLM-5/4.7:** Rate limits generosos (~100+ req/min).
- **Nova Pro:** Más restrictivo (~20-50 req/min según región).
- **Mitigación actual:** Semaphore(5) + exponential backoff en `bedrock.py`.
- **Riesgo residual:** Con 5+ usuarios generando parrillas de 10 posts al mismo tiempo, el Semaphore global de 5 se satura. Necesita queue con priorización.

### 10.2 Costos de Flux/Kling
- **Flux Kontext Pro:** ~$0.05-0.10/imagen × 10 posts = $0.50-1.00 por parrilla.
- **Nano Banana 2:** ~$0.03-0.05/imagen × 10 posts = $0.30-0.50 por parrilla.
- **Kling video:** ~$0.10-0.30/video × 10 videos = $1.00-3.00 por parrilla con videos.
- **Riesgo:** Sin metering ni limites per-agency, un solo usuario podría generar cientos de dólares en un día.
- **Mitigación recomendada:** Fase 3 (imágenes solo al aprobar) + rate limits per-agency.

### 10.3 Timeouts en generación larga
- **Post individual:** Flux timeout 300s + Nano Banana 120s = ~7 min worst case.
- **Parrilla de 10 posts secuenciales:** ~70 minutos worst case (actual).
- **Con paralelización (Fase 2):** ~15-20 min worst case.
- **Riesgo:** `BackgroundTasks` no tiene timeout global. Si un background task se cuelga, no hay mecanismo de cleanup.

### 10.4 Concurrencia
- **Background tasks** comparten event loop con request handlers. Una ráfaga de generaciones puede degradar latencia de endpoints simples.
- **Supabase SDK sync** — aunque encapsulado en `async`, las operaciones son sync y podrían bloquear si el response time de Supabase se degrada.
- **Sessions in-memory** — no funciona con múltiples workers (uvicorn --workers > 1) ni con deploy horizontal.

### 10.5 Storage Costs
- **Post images:** ~200KB-1MB per PNG × 10 posts × N parrillas.
- **Videos:** ~5-20MB per video × N videos.
- **Base images (sin overlay):** se guardan además del rendered final, duplicando storage.
- **Sin cleanup policy** — imágenes de posts eliminados se quedan en storage.

### 10.6 Datos sensibles en logs
- **Riesgo bajo actual** — no hay leak directo de API keys en logs (verificado).
- **Riesgo medio:** Error responses de Bedrock/Gemini/fal.ai se loguean y podrían contener info del modelo o del request (e.g., contenido de usuario).
- **Recomendación:** Truncar response bodies a 200 chars en logs de error.

### 10.7 Seguridad de endpoints
- **9 endpoints sin autenticación** que consumen recursos pagados (Vertex AI, Bedrock).
- **CORS wildcard** permite requests desde cualquier dominio.
- **Sin rate limiting** — vulnerable a abuse y DDoS a nivel de aplicación.
- **SSL verification disabled** en la conexión a Postgres.

### 10.8 Resiliencia
- **Sin circuit breaker** para servicios externos. Si fal.ai está degradado, los posts fallarán uno por uno lentamente.
- **Sin health checks** para servicios externos en startup.
- **Sin fallback de Flux → Vertex AI** en caso de falla de fal.ai (sí existe al revés: si no hay product images, usa Vertex).
