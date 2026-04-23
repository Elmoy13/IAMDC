# Auditoría Backend — Flujo de Parrillas (Generación de Posts)

**Fecha:** 2026-04-23
**Auditor:** GitHub Copilot (Claude Opus 4.6)
**Scope:** Código backend — análisis estático sin acceso a DB ni logs de producción

---

## A. Diagrama del Flujo Actual

### Flujo 1: Two-Phase (copy primero, imágenes después) — `generate-copy-only`

```
1. Frontend POST /api/v1/posts/generate-copy-only
   Body: SmartBatchRenderRequest { brand, campaign, posts_config[], draft_id?, ... }
   
2. Backend (posts.py L507):
   a. Detecta idioma (auto → detect_language())
   b. Si draft_id: lee config de parrilla_drafts, cambia draft status → "generating"
      ⚠️ Si falla, silently drops draft_id (try/except → draft_id = None)
   c. Crea job en generation_jobs (status: "processing")
   d. Crea N placeholder rows en generated_posts (status: "generating")
   e. Lanza background task: post_pipeline.generate_copy_batch()

3. Response inmediata: { job_id, total_posts, status: "processing" }

4. Background (post_pipeline.py L44):
   a. enrich_context_from_supabase(brand_id=None, draft_id=draft_id)
      → Lee selected_product_ids del draft
      → Lee brand_products para product_analysis
      ⚠️ brand_id=None siempre → NUNCA lee datos de brands table
   b. content_generator.generate_post_content() → Bedrock GLM-5 (fallback chain)
      → Un solo LLM call para N posts → JSON array
   c. Para cada post: update_post_copy_success(status="success", image_status="pending")
   d. Crea version 1 (copy only, no image)
   e. complete_job() → job status="completed", draft status="generated"

5. Frontend polls GET /api/v1/posts/job/{job_id}
   → Recibe { job: {...}, posts: [{status, headline, body, cta, image_prompt, ...}] }

6. User revisa copy y aprueba → POST /api/v1/posts/{post_id}/approve-and-generate-image
   O bulk: POST /api/v1/posts/job/{job_id}/generate-all-approved-images

7. Background: post_pipeline.generate_image_for_post()
   a. optimize_image_prompt() (ES→EN via GLM-5)
   b. Flux Kontext Pro (si hay product_images) o Vertex Imagen 3 (fallback)
   c. Nano Banana overlay (logo/text si configurado)
   d. Upload a Supabase Storage
   e. Update post: image_status="ready", rendered_image_url=url
```

### Flujo 2: Full Pipeline (legacy, copy + images juntos) — `generate`

```
1. Frontend POST /api/v1/posts/generate
   Body: SmartBatchRenderRequest (idéntico)

2. Backend (posts.py L420):
   a-e. Igual que Flujo 1

3. Background: post_pipeline.generate_full_pipeline()
   a. generate_copy_batch() (Phase 1)
   b. Auto-aprueba todos los posts exitosos
   c. Re-abre job (status: "processing")
   d. generate_images_batch() (Phase 2, paralelo con Semaphore(3))
   e. complete_job()
```

### Flujo 3: Sync Render (legacy, devuelve imágenes inline) — `render-batch`

```
1. POST /api/v1/posts/render-batch
   → LLM genera copy → Vertex/Flux genera imagen → HTML template → Playwright → PNG
   → Response síncrona con data URLs (NO usa Supabase)
```

---

## B. Dónde Se Rompe — Hipótesis de "0 Posts"

### Hallazgo Principal: El job completa "exitosamente" pero los posts pueden estar todos en estado "error"

El toast "Copy generado · 0 posts listos para revisar" sugiere que:
1. El endpoint `/generate-copy-only` responde 200 con `job_id` ✅
2. El job se crea correctamente ✅
3. Los placeholders se crean (status: "generating") ✅
4. El background task falla en `generate_copy_batch()`...
5. ...pero el job se marca como "completed" de todas formas

### Puntos de falla probables (ordenados por probabilidad):

#### 🔴 Hipótesis 1: `content_generator.generate_post_content()` falla — Bedrock error

**Archivo:** [app/services/post_pipeline.py](app/services/post_pipeline.py#L72)

Si `generate_post_content()` lanza una excepción (ej: todos los modelos del fallback chain fallan — GLM-5, GLM-4.7, Nova Pro), se cae al `except` exterior en línea 122:
```python
except Exception as exc:
    logger.error("copy_batch_failed", job_id=job_id, error=str(exc))
    await supabase_client.fail_job(job_id, str(exc))
```

Esto marcaría el job como **"failed"** y los posts quedarían en **"generating"** (nunca actualizados).

**Pero:** El frontend muestra "Copy generado" — lo que sugiere que el job SÍ completa. Esto descarta un fallo total en el LLM. A menos que el frontend interprete el response 200 del endpoint como "éxito" sin esperar al background task.

#### 🔴 Hipótesis 2: `update_post_copy_success()` falla silenciosamente — Supabase error

**Archivo:** [app/services/post_pipeline.py](app/services/post_pipeline.py#L95)

Cada post se actualiza individualmente. Si `update_post_copy_success()` falla (ej: columna faltante en DB como `image_status` que fue agregada después, o RLS policy bloqueando), se cae al catch individual:
```python
except Exception as exc:
    logger.error("copy_post_failed", index=idx, post_id=post_id, error=str(exc))
    await supabase_client.update_post_error(post_id, str(exc))
```

El job sigue como "completed" pero TODOS los posts quedan en status "error". El frontend filtra por `status === "success"` → **0 posts visibles**.

#### 🟡 Hipótesis 3: Frontend llama `/generate` (full pipeline) en vez de `/generate-copy-only`

Si el frontend usa el endpoint full pipeline, el flujo intenta generar imágenes después del copy. Si la imagen falla para todos (ej: Flux key inválida, Vertex quota), los posts quedan con `status: "success"` pero `image_status: "error"`. Si el frontend filtra por `image_status === "ready"` → 0 posts.

#### 🟡 Hipótesis 4: El Supabase client es SYNC bloqueando el event loop

**Archivo:** [app/services/supabase_client.py](app/services/supabase_client.py)

TODAS las funciones son `async def` pero usan el cliente **sync** de Supabase. Cada operación bloquea el event loop. En un `BackgroundTasks` de FastAPI, esto normalmente funciona (ejecuta en el mismo thread), pero puede causar timeouts si hay muchas operaciones concurrentes o si el response de Supabase es lento.

#### 🟢 Hipótesis 5: `enrich_context_from_supabase()` con `brand_id=None`

**Archivo:** [app/services/post_pipeline.py](app/services/post_pipeline.py#L61)

El pipeline SIEMPRE pasa `brand_id=None` a `enrich_context_from_supabase()`. La función solo lee la tabla `brands` si `brand_id` es truthy. Esto significa que **nunca se enriquece con datos de marca de Supabase** (logo analysis, colores persistidos). Solo se usan los datos que vienen en el payload.

Esto NO causa el bug de "0 posts" pero sí afecta calidad y es deuda técnica clara.

### ⚠️ Verificación necesaria (requiere acceso a prod):

```sql
-- 1. Verificar si el job existe y su status
SELECT id, status, error_message, total_posts, completed_posts, draft_id
FROM generation_jobs
WHERE draft_id = 'ca2abbd7-80aa-47f8-95aa-344d335a7f20'
ORDER BY created_at DESC
LIMIT 5;

-- 2. Verificar si hay posts y su status
SELECT id, job_id, status, error_message, headline, image_status
FROM generated_posts
WHERE job_id IN (
  SELECT id FROM generation_jobs
  WHERE draft_id = 'ca2abbd7-80aa-47f8-95aa-344d335a7f20'
)
ORDER BY created_at DESC;

-- 3. Verificar el draft  
SELECT id, status, config, brand_id, selected_product_ids
FROM parrilla_drafts
WHERE id = 'ca2abbd7-80aa-47f8-95aa-344d335a7f20';
```

**Con estos resultados podemos confirmar cuál hipótesis es la correcta:**
- Si `generation_jobs.status = "failed"` → Hipótesis 1 (LLM fail)
- Si `generated_posts.status = "error"` para todos → Hipótesis 2 (DB write fail)
- Si `generated_posts.status = "success"` pero `image_status = "error"` → Hipótesis 3
- Si no hay `generation_jobs` con ese `draft_id` → el endpoint nunca fue llamado correctamente
- Si `generation_jobs.status = "completed"` y `generated_posts.status = "success"` → bug de frontend (los datos SÍ están en DB)

---

## C. Estado de la DB

**No tengo acceso directo a la DB de producción.** Las queries SQL arriba deben ejecutarse en Supabase para confirmar la causa raíz.

### Esquema de tablas (inferido del código):

| Tabla | Columnas clave |
|-------|---------------|
| `parrilla_drafts` | id, agency_id, brand_id, user_id, title, status, chat_messages, config, selected_product_ids, last_step |
| `generation_jobs` | id, total_posts, completed_posts, brand_name, campaign_description, status, error_message, language, agency_id, draft_id, config |
| `generated_posts` | id, job_id, index, platform, format, status, error_message, headline, body, cta, image_prompt, image_prompt_en, rendered_image_url, base_image_url, image_status, approval_status, approved_at, video_url, video_status, video_error, motion_prompt, current_version_number, edit_status |
| `post_versions` | id, post_id, version_number, is_current, headline, body, cta, image_prompt, rendered_image_url, base_image_url, user_message, ai_response, change_scope |
| `post_edit_chat` | id, post_id, role, content, version_id |

### Estado State Machine:

```
parrilla_drafts.status:   draft → generating → generated
generation_jobs.status:    processing → completed | failed
generated_posts.status:    generating → success | error
generated_posts.image_status: (null) → pending → generating → ready | error
generated_posts.approval_status: (null) → approved
```

---

## D. Lista de Bugs / Deuda Técnica

### 1. [CRÍTICO] Job completa como "completed" incluso si TODOS los posts fallan

**Archivo:** [app/services/post_pipeline.py](app/services/post_pipeline.py#L119)

En `generate_copy_batch()`, si cada post individual falla en el `try/except` interno, el loop continúa y luego llama `complete_job()`. Un job con 3/3 posts en status "error" se marca como "completed". El frontend probablemente muestra "Copy generado" basándose en el job status, pero al listar posts con `status === "success"` encuentra 0.

**Fix:** Verificar cuántos posts son "success" antes de completar el job. Si 0 → `fail_job()`.

### 2. [CRÍTICO] `brand_id` nunca se pasa a `enrich_context_from_supabase()` en el pipeline

**Archivo:** [app/services/post_pipeline.py](app/services/post_pipeline.py#L61)

```python
brand_ctx, pa_enriched, _products = (
    await content_generator.enrich_context_from_supabase(
        brand_id=None,  # ← SIEMPRE None
        draft_id=payload.draft_id,
    )
)
```

La tabla `parrilla_drafts` tiene `brand_id`, pero nunca se lee para pasarlo a `enrich_context_from_supabase()`. La función debería leer `brand_id` del draft si no viene directo.

**Fix:** Leer `brand_id` del draft en la consulta de enrich, o agregar `brand_id` al schema `SmartBatchRenderRequest`.

### 3. [ALTO] Supabase client es sync bloqueando el asyncio event loop

**Archivo:** [app/services/supabase_client.py](app/services/supabase_client.py)

Todas las funciones son `async def` pero ejecutan HTTP sync (Supabase sync client). Cada llamada bloquea el event loop ~50-200ms. En un background task con 3 posts × ~5 DB calls cada uno = 15 llamadas, el loop se bloquea ~1.5-3 segundos acumulados.

**Impact:** No causa el bug directamente, pero puede causar timeouts en concurrencia alta y degradar el performance de todo el servidor.

**Fix:** Migrar a `supabase.acreate_client()` o wrapping con `asyncio.to_thread()`.

### 4. [ALTO] Draft linkage falla silenciosamente

**Archivo:** [app/api/v1/posts.py](app/api/v1/posts.py#L455)

```python
except Exception as exc:
    logger.warning("draft_link_failed", draft_id=draft_id, error=str(exc))
    draft_id = None  # ← Silently drops the draftf association
```

Si la query a `parrilla_drafts` falla (ej: tabla no existe en Supabase, FK rota, timeout), el job se crea **sin draft_id**. El draft queda en status "draft" forever, nunca se actualiza a "generated". El usuario no sabe que la asociación se perdió.

**Fix:** No hacer `draft_id = None`. Si el draft no se puede leer, devolver error 500 al usuario.

### 5. [ALTO] No hay endpoint `GET /api/v1/drafts/{draft_id}/posts`

El frontend necesita listar posts de un draft. Hoy tiene que:
1. Buscar el `generation_jobs` con `draft_id` 
2. Luego buscar `generated_posts` con `job_id`

No hay endpoint directo. Si la FK `generation_jobs.draft_id → parrilla_drafts.id` no se persistió (por el bug #4), el frontend no puede encontrar los posts.

**Fix:** Crear endpoint `GET /drafts/{draft_id}/posts` que haga JOIN jobs → posts.

### 6. [MEDIO] `_generate_posts_background()` (legacy) es código duplicado del pipeline

**Archivo:** [app/api/v1/posts.py](app/api/v1/posts.py#L710)

La función `_generate_posts_background()` tiene ~100 líneas de lógica duplicada que hace lo mismo que `PostPipeline.generate_full_pipeline()` pero con una implementación diferente (secuencial vs. pipeline). El endpoint `/generate` usa `post_pipeline.generate_full_pipeline()` pero la función legacy sigue en el archivo.

**Fix:** Borrar `_generate_posts_background()` si ya no se usa (verificar que ningún path la invoque).

### 7. [MEDIO] Columna `image_status` puede no existir en DB

Si `generated_posts` fue creada antes del Sprint 3.5in de two-phase pipeline, la columna `image_status` puede no existir. `create_post_placeholder()` no la setea. `update_post_copy_success()` sí la setea como "pending". Si la columna no existe, el UPDATE falla → Hipótesis 2 del bug.

**Fix:** Verificar que la migration SQL incluyó `image_status`, `approval_status`, `approved_at` en `generated_posts`.

### 8. [MEDIO] `invoke_vision()` no tiene retry

**Archivo:** [app/providers/bedrock.py](app/providers/bedrock.py#L162)

A diferencia de `invoke()` que tiene retry con backoff para throttling, `invoke_vision()` falla al primer error. Esto afecta al `edit_director` y `brand_analyzer` que dependen de visión.

### 9. [BAJO] El campo `config` del job no se persiste del payload completo

**Archivo:** [app/api/v1/posts.py](app/api/v1/posts.py#L628)

Cuando el usuario aprueba un post y dispara image generation, el endpoint lee `job_config = job.get("config")` para extraer brand/product_images. Pero el `config` solo se persiste si viene del draft (`draft_config`). Si no hay draft o falló el linkage, `config` es `None` → el approve endpoint no tiene brand data para generar la imagen.

**Fix:** Persistir siempre el payload completo como config del job, no solo la config del draft.

### 10. [BAJO] `enrich_context_from_supabase()` no lee `brand_id` del draft

La función recibe `draft_id` pero solo lee `selected_product_ids` del draft. No lee `brand_id` para después buscar en `brands`. Si se le pasa `brand_id=None` + `draft_id=X`, los datos de marca del Supabase nunca se cargan.

---

## E. Propuesta de Fix

### Fix Inmediato (eliminar bug "0 posts") — Small

1. **Verificar en DB** qué status tienen los posts y el job del draft referenciado
2. Si confirma Hipótesis 2 (DB write fail): agregar migration para columnas `image_status`, `approval_status`, `approved_at` en `generated_posts` (si faltan)
3. Si confirma Hipótesis 1 (LLM fail): revisar logs de Bedrock, verificar que las credenciales AWS y los model IDs son correctos

### Fix de Robustez — Medium

1. **`generate_copy_batch()` valida success count** antes de `complete_job()`:
   ```python
   success_count = sum(1 for ... if post["status"] == "success")
   if success_count == 0:
       await supabase_client.fail_job(job_id, "All posts failed")
   else:
       await supabase_client.complete_job(job_id)
   ```

2. **Persistir config completa en job** (no solo draft config):
   ```python
   config = {
       "brand": payload.brand.model_dump(),
       "product_images": payload.product_images,
       "include_logo_in_image": payload.include_logo_in_image,
       "include_text_in_image": payload.include_text_in_image,
   }
   ```

3. **No silenciar draft linkage failure** — retornar 500 si el draft existe pero no se puede leer

4. **Crear endpoint `GET /drafts/{draft_id}/posts`**

### Fix Estructural — Large

1. Migrar `supabase_client` a async client o `to_thread()`
2. Propagar `brand_id` correctamente: draft → enrich → content generator
3. Eliminar `_generate_posts_background()` duplicado
4. Agregar retry a `invoke_vision()`
5. Tests e2e para los endpoints HTTP (no solo unit tests con mocks)

### ¿SQL Migration necesaria?

**Posiblemente sí.** Verificar en Supabase si `generated_posts` tiene:
- `image_status` (TEXT, default NULL)
- `approval_status` (TEXT, default NULL)  
- `approved_at` (TIMESTAMPTZ, default NULL)
- `image_prompt_en` (TEXT, default NULL)
- `base_image_url` (TEXT, default NULL)

Si alguna falta, el `update_post_copy_success()` que setea `image_status = "pending"` falla silenciosamente (el Supabase SDK no lanza error por columnas inexistentes, simplemente ignora el campo — **verificar este comportamiento**).

---

## F. Archivos Clave del Feature

| Archivo | Rol | Líneas clave |
|---------|-----|-------------|
| [app/api/v1/posts.py](app/api/v1/posts.py) | Endpoints HTTP — generate, generate-copy-only, approve, job status, edit, video | L420 (generate), L507 (generate-copy-only), L590 (approve), L690 (job status) |
| [app/api/v1/drafts.py](app/api/v1/drafts.py) | CRUD de parrilla_drafts | Todo el archivo |
| [app/services/post_pipeline.py](app/services/post_pipeline.py) | Orquestador two-phase pipeline | L44 (copy batch), L131 (image single), L257 (image batch), L305 (full pipeline) |
| [app/services/content_generator.py](app/services/content_generator.py) | LLM call para copy (GLM-5) | L318 (generate_post_content), L262 (enrich_context) |
| [app/services/supabase_client.py](app/services/supabase_client.py) | CRUD Supabase (sync!) | L31 (create_job), L115 (create_placeholder), L403 (update_copy_success) |
| [app/providers/bedrock.py](app/providers/bedrock.py) | Bedrock API with fallback chain | L131 (invoke_with_fallback) |
| [app/services/prompt_optimizer.py](app/services/prompt_optimizer.py) | ES→EN image prompt | Todo |
| [app/services/flux_kontext.py](app/services/flux_kontext.py) | Flux Kontext Pro (image gen) | - |
| [app/services/nano_banana.py](app/services/nano_banana.py) | Logo/text overlay | - |
| [app/providers/vertex_imagen.py](app/providers/vertex_imagen.py) | Vertex Imagen 3 (fallback) | - |
| [app/services/edit_director.py](app/services/edit_director.py) | Nova Pro Vision edit analysis | - |
| [app/services/post_regenerator.py](app/services/post_regenerator.py) | Post re-generation | - |
| [app/schemas/post.py](app/schemas/post.py) | Pydantic schemas | L112 (SmartBatchRenderRequest) |
| [app/schemas/draft.py](app/schemas/draft.py) | Draft schemas | Todo |
| [tests/test_post_pipeline.py](tests/test_post_pipeline.py) | Unit tests (mocked) | 6 tests, all pass with mocks |
| [tests/test_content_generator.py](tests/test_content_generator.py) | Content gen tests (mocked) | - |

---

## G. Respuestas Explícitas a Preguntas del Brief

### ¿El flujo es de 2 fases o 1 fase?

**Ambos existen:**
- `/generate-copy-only` → 2 fases (copy → approve → images)
- `/generate` → 1 fase (copy + auto-approve + images en batch)
- `/render-batch` → sync, todo en un request (legacy)

### ¿Hay paso de "aprobar prompts"?

**Sí**, implementado correctamente:
- Phase 1: `POST /generate-copy-only` → posts con `status: "success"`, `image_status: "pending"`
- Approve individual: `POST /posts/{id}/approve-and-generate-image`
- Approve bulk: `POST /posts/job/{id}/generate-all-approved-images`

### ¿El optimizador ES→EN está activo?

**Sí**, en Phase 2 (`generate_image_for_post`). NO se usa en Phase 1 (no es necesario, solo genera copy).

### ¿El GLM-5 → GLM-4.7 → Nova Pro fallback está funcionando?

**Implementado correctamente** en `bedrock.invoke_with_fallback()`. Retry 3x por modelo con backoff exponencial.

### ¿Hay feature flags?

**No.** No hay toggles para habilitar/deshabilitar el pipeline, la generación de imágenes, ni la two-phase mode.

### ¿Hay tests e2e del flujo?

**No.** Solo unit tests con mocks. No hay tests de integración con Supabase real ni Bedrock real.

### ¿El flujo maneja fallos parciales?

**Parcialmente.** Posts individuales pueden fallar sin detener el batch, pero el job se marca como "completed" aunque todos fallen (Bug #1).

### ¿Hay rate limiting bloqueando?

**No hay rate limiting propio.** Bedrock tiene retry para ThrottlingException. Flux usa Semaphore(3). No hay rate limiter en los endpoints.

---

## H. Conclusión

El backend del flujo de parrillas está **arquitectónicamente completo** — soporta two-phase generation, approval workflow, image generation, editing, y video. El código es legible y tiene tests unitarios.

El bug de "0 posts" muy probablemente es uno de:
1. **Fallo silencioso en el background task** (LLM, DB write, o columna faltante) que marca el job como "completed" sin posts exitosos
2. **Frontend interpretando el response del endpoint como éxito** sin esperar al background task
3. **Draft linkage fallida** que causa que el frontend no pueda encontrar los posts del draft

**Acción inmediata requerida:** Ejecutar las queries SQL de la sección C en producción para determinar cuál es la causa raíz exacta. Con esos datos, el fix es Small (1-2 horas).
