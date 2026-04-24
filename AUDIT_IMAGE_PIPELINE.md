# Auditoría: Pipeline de Imagen (logo + producto + texto)

**Fecha:** 2026-04-23  
**Draft de referencia:** `56b9e062-5877-4b4f-a2e9-7c368a4e0ebd`  
**Agency:** `f96b6228-aee2-416f-b9cf-fe9251f8483b`  
**Brand:** `d05274c7-e8ee-4f5c-9fb1-06e4c0c071ee`

---

## Sección A — Schema del payload + job config

### A1. Schema `SmartBatchRenderRequest` completo

**Archivo:** `app/schemas/post.py` líneas 139–158

```python
class SmartBatchRenderRequest(BaseModel):
    brand: BrandInputFull
    campaign: CampaignInput
    product_images: list[str] = Field(default=[])
    include_logo_in_image: bool = Field(default=False)
    include_text_in_image: bool = Field(default=False)
    logo_analysis: dict | None = Field(default=None)
    product_analysis: dict | None = Field(default=None)
    posts_config: list[PostConfigItem] = Field(min_length=1)
    language: str = Field(default="auto", pattern="^(es|en|auto)$")
    chat_messages: list[dict] | None = Field(default=None)
    draft_id: str | None = Field(default=None)
```

### A2. ¿Se recibe `include_logo_in_image` y `include_text_in_image`?

**SÍ**, con esos nombres exactos. Líneas 143–144 de `app/schemas/post.py`.

Defaults: ambos en `False`. El frontend debe enviarlos como `true` explícitamente.

### A3. ¿Se recibe `product_images` o `selected_product_ids`?

**`product_images: list[str]`** — campo del schema, contiene strings base64 (data URLs) enviados directamente desde el frontend. Línea 142.

**`selected_product_ids`** NO existe en el schema del request. Existe en la tabla `parrilla_drafts.selected_product_ids`, pero solo se usa para enriquecer contexto LLM (vision_analysis), **nunca para obtener URLs de imagen de producto para Flux**.

### A4. Job config persistido

**Archivo:** `app/api/v1/posts.py` líneas 478–485

```python
job_config = {
    "brand": payload.brand.model_dump(),
    "campaign": payload.campaign.model_dump(),
    "product_images": payload.product_images or [],
    "include_logo_in_image": payload.include_logo_in_image,
    "include_text_in_image": payload.include_text_in_image,
    "language": payload.language,
}
```

Se guarda en `generation_jobs.config` (columna JSON) vía `supabase_client.create_job()`.

**HALLAZGO CRÍTICO:** `product_images` contiene lo que mande el frontend como base64. Si el frontend NO envía las imágenes del producto en este campo (porque las tiene en `brand_products.image_url`), el array llega vacío: `[]`. Y el pipeline cae al branch text-to-image sin referencia de producto.

---

## Sección B — Enriquecimiento brand + producto

### B1. `enrich_context_from_supabase()` — qué lee del brand

**Archivo:** `app/services/content_generator.py` líneas 282–292

```python
result = (
    client.table("brands")
    .select("name, vision_analysis, primary_color, secondary_color, accent_color, font_family")
    .eq("id", brand_id)
    .maybe_single()
    .execute()
)
```

Lee: `name`, `vision_analysis`, `primary_color`, `secondary_color`, `accent_color`, `font_family`.  
**NO lee:** `logo_url`.

### B2. Qué lee de `brand_products`

**Archivo:** `app/services/content_generator.py` líneas 297–316

```python
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
```

Selecciona `*` de `brand_products`, pero **solo usa `vision_analysis`** del primer producto. **`image_url` se recupera pero nunca se pasa al pipeline de imagen.** Los productos se devuelven en el tuple pero `post_pipeline.py` los ignora (variable `_products`).

### B3. ¿El `brand_id` se propaga?

**Archivo:** `app/services/post_pipeline.py` líneas 55–65

```python
brand_id = None
if payload.draft_id:
    draft = await supabase_client.get_draft(payload.draft_id)
    if draft:
        brand_id = draft.get("brand_id")
```

El `brand_id` depende de que:
1. `payload.draft_id` esté presente
2. El draft exista en `parrilla_drafts`
3. El draft tenga un `brand_id`

**Sobre el error `enrich_brand_failed error={'message': 'Missing response', 'code': '204'}`:**

Código 204 = la query Supabase con `.maybe_single()` no encontró filas. Esto significa que:
- O bien `brand_id` era None (draft sin brand)
- O bien `brand_id` apuntaba a un brand que no existe en la tabla `brands`

**El pipeline CONTINUÓ sin contexto del brand**, porque el error se captura con `try/except` y solo genera un `logger.warning` (línea 293 de content_generator.py). Resultado: todos los campos del `CONTENT_PROMPT` se rellenan con `"no analizado"`.

### B4. ¿Los colores del brand se pasan al prompt de imagen?

**Al prompt de copy (CONTENT_PROMPT):** SÍ — líneas 86–88 de `post_pipeline.py`:

```python
brand_colors={
    "primary": payload.brand.primary_color,
    "secondary": payload.brand.secondary_color,
    "accent": payload.brand.accent_color,
}
```

Estos se inyectan en el `CONTENT_PROMPT` como:
```
Colores: primario {color_primary}, secundario {color_secondary}, acento {color_accent}
```

**Al prompt de Flux/image model:** NO. El `optimize_image_prompt()` recibe `brand_context=brand` pero solo lee `brand.get('name')` y `brand.get('tone')` — **ambos campos NO existen en el dict** `brand_dict` que se construye en línea 367:

```python
brand_dict = {
    "logo_b64": payload.brand.logo_b64,
    "primary_color": payload.brand.primary_color,
    "secondary_color": payload.brand.secondary_color,
    "accent_color": payload.brand.accent_color,
}
```

No hay `name` ni `tone` en `brand_dict`. El optimizer los renderiza como `"Unknown"` y `"professional"` (defaults).

**Los colores del brand (#969693, #7C7C74, #7C7474) nunca llegan a Flux.** Ni en el prompt ni como parámetro. Flux genera escenas con cualquier paleta.

---

## Sección C — Generación del `image_prompt`

### C1. Dónde se genera el `image_prompt`

**Archivo:** `app/services/content_generator.py`, función `generate_post_content()` línea 324.

El `CONTENT_PROMPT` (líneas 27–137) instruye al LLM a generar un array JSON donde cada objeto incluye `image_prompt`.

### C2. System prompt completo para generación de `image_prompt`

El system prompt del LLM es mínimo (`app/services/content_generator.py` línea 401):

```python
system_prompt = (
    "You are a senior creative director and social media marketing expert. "
    "Always respond with valid JSON only. Never wrap your response in markdown code fences."
)
```

El user prompt (`CONTENT_PROMPT`) es lo que contiene las instrucciones. Fragmento relevante para image_prompt (líneas 82–137):

```
4. "image_prompt": Descripción de la escena donde va el producto.

   REGLA PRINCIPAL — LA ESCENA DEBE REFLEJAR LA CAMPAÑA:
   ...
   REGLA ABSOLUTA: NO incluir texto, letras, palabras ni writing en la imagen.
   ...
   El producto del cliente se proporcionará como imagen de referencia.
   Empieza SIEMPRE con "This product" para que Flux sepa qué es la referencia.
   Describe: dónde está el producto, qué hay alrededor, iluminación, ambiente.
   NO describas el producto mismo (Flux ya tiene la foto real).
```

**¿Instruye a referenciar "a bottle of BacachitoFeliz tequila"?**  
NO directamente. El prompt dice "This product" genéricamente. Los datos del producto se inyectan en las variables del template:
- `{product_type}` → `pa.get("product_type", "no analizado")`
- `{product_description}` → `pa.get("product_description", "no analizado")`

**Si el enrich_brand_failed (204) ocurrió**, estos campos se rellenaron con `"no analizado"`, por lo que el LLM no supo qué producto es.

**¿Instruye a usar la paleta de colores?**  
Las variables `{color_primary}`, `{color_secondary}`, `{color_accent}` están en el prompt, bajo `ANÁLISIS DE LA MARCA`, pero el prompt de imagen dice explícitamente **"NO describas el producto mismo"** y no menciona "usa estos colores en la escena". Los colores están disponibles para el LLM pero no hay instrucción explícita de usarlos en el `image_prompt`.

### C3. Ejemplo real de `image_prompt_en`

No es posible obtener esto sin acceso a la DB en producción. Requiere: `SELECT image_prompt, image_prompt_en FROM generated_posts WHERE job_id = '<id>' LIMIT 3`.

---

## Sección D — Flujo exacto Flux/Nano Banana

### D1. Función que genera imágenes

**Archivo:** `app/services/post_pipeline.py`, `generate_image_for_post()` líneas 147–260

### D2. Decisión Flux Kontext Pro vs Flux Pro 1.1

**Archivo:** `app/services/post_pipeline.py` líneas 192–244

```python
if product_image_urls:                      # ← IF product images exist
    product_url = product_image_urls[0]
    flux_image_url = await generate_image_with_reference(
        prompt=prompt_en,
        reference_image_url=product_url,    # ← Kontext Pro (image-to-image)
        aspect_ratio=aspect_ratio,
    )
else:                                       # ← NO product images
    flux_image_url = await generate_image_with_reference(
        prompt=prompt_en,
        reference_image_url="",             # ← Flux Pro 1.1 (text-to-image)
        aspect_ratio=aspect_ratio,
    )
```

La decisión se toma en `flux_kontext.py` línea 52: `use_kontext = bool(reference_image_url)`.

**¿Está implementado?** SÍ, el código existe. Pero depende de que `product_images` NO esté vacío.

### D3. ¿De dónde se lee `product_image_url` para Flux?

**NOT from DB.** Se lee exclusivamente de `product_images` del payload/job_config, que son base64 strings del request original del frontend (`SmartBatchRenderRequest.product_images`).

`brand_products.image_url` (la URL pública guardada al analizar el producto) **NUNCA se lee en el pipeline de imagen**. Solo se lee `vision_analysis` para enriquecer el prompt del LLM de copy.

### D4. ¿Cuándo se ejecuta Nano Banana?

**Archivo:** `app/services/post_pipeline.py` líneas 211–229

```python
# Nano Banana overlay if requested
if include_logo_in_image or include_text_in_image:
    logo_url = None
    if include_logo_in_image and brand.get("logo_b64"):
        logo_url = await upload_image_to_fal(brand["logo_b64"])
    enhanced_url = await nano_banana.enhance_post_image(...)
```

**HALLAZGO CRÍTICO:** Nano Banana **SOLO se ejecuta dentro del branch `if product_image_urls:`** (línea 192). Si no hay product images, el código cae al `else:` (línea 232) y **Nano Banana nunca se llama**, incluso si `include_logo_in_image=True` y `include_text_in_image=True`.

```
if product_image_urls:
    # ...Flux Kontext...
    if include_logo or include_text:   ← Nano Banana aquí ✅
        ...
    else:
        image_b64 = base_b64
else:
    # ...Flux Pro 1.1... (text-to-image)
    image_b64 = base_b64               ← Nano Banana NUNCA aquí ❌
```

### D5. Prompt de Nano Banana

**Archivo:** `app/services/nano_banana.py` líneas 62–98

```python
# Logo overlay:
"Integrate the logo from the second reference image naturally into the scene. "
"Place it clearly visible on a surface in the scene such as a coaster, "
"a small framed sign, a napkin, or a neon sign on the wall. "
"The logo must be sharp, fully visible, and recognizable."

# Text overlay:
"Add the following text in {lang_name} with perfect typography "
"at the bottom of the image. "
"The headline text must say exactly: '{headline}'. "
"Use a premium, clean sans-serif font. "
"The text should be white or light colored with a subtle dark gradient "
"or semi-transparent dark bar behind it for readability."

# CTA button:
"Below the headline, add a small button-style element "
"with the text '{cta}' using the brand color {primary_color}."
```

**¿Incluye la URL del logo como reference_image?** SÍ — línea 68: `image_urls = [base_image_url]` + si logo: `image_urls.append(logo_url)`.

**¿Incluye headline/CTA?** SÍ — como texto en el prompt.

**¿Instrucciones de posicionamiento?** Parcialmente: "at the bottom of the image" para texto, "on a surface in the scene" para logo. No hay "bottom-right" o "top-center" explícito.

---

## Sección E — Llamadas a fal.ai esperadas (análisis de código)

### E1. Modelos usados

Según el código, para cada post:

| Condición | Modelo 1 | Modelo 2 | Total llamadas |
|---|---|---|---|
| `product_images` + (logo OR text) | Flux Kontext Pro | Nano Banana 2 Edit | 2 |
| `product_images` + NO logo/text | Flux Kontext Pro | — | 1 |
| NO `product_images` (cualquier toggle) | Flux Pro 1.1 | — | 1 |

### E2. Para 3 posts sin `product_images`:
- 3 llamadas a Flux Pro 1.1 (text-to-image)
- 0 llamadas a Nano Banana
- Total: **3 llamadas**

Para verificar la parrilla real, se necesitan logs de producción o la columna `image_prompt_en` de los posts.

---

## Sección F — Analyze-vision del producto

### F1. Endpoint de análisis de producto

**Archivo:** `app/api/v1/product.py` línea 33

```python
@router.post("/analyze")
async def analyze_product(payload: ProductAnalyzeRequest, agency):
```

Hace vision analysis del producto con Nova Pro Vision, retorna JSON con `product_type`, `product_description`, `key_features`, `style`, `best_angles`, `ideal_settings`, `photography_style`.

Si `payload.brand_id` y `payload.persist != False`: sube la imagen a Supabase Storage, inserta en `brand_products` con:
```python
row = {
    "brand_id": payload.brand_id,
    "name": payload.product_name or result.get("product_type", "Product"),
    "image_url": image_url,           # ← URL pública del storage
    "storage_path": storage_path,
    "vision_analysis": result,         # ← JSON del análisis
    "analyzed_at": "now()",
    "display_order": payload.display_order,
}
```

### F2. Schema de `brand_products`

Columnas confirmadas por el INSERT y el `SELECT *`:
- `id` (UUID, auto)
- `brand_id` (UUID, FK)
- `name` (text)
- `image_url` (text) — URL pública del producto en storage
- `storage_path` (text)
- `vision_analysis` (jsonb) — resultado del análisis de Nova Pro Vision
- `analyzed_at` (timestamp)
- `display_order` (integer)

No existe `photo_url` ni `product_image_url`. La columna se llama `image_url`.

### F3. ¿`vision_analysis` se usa al generar el `image_prompt`?

**SÍ, pero con condiciones.** En `content_generator.py` líneas 297–316, `vision_analysis` se lee de `brand_products` (via `selected_product_ids` del draft) y se pasa como `product_analysis` al `CONTENT_PROMPT`.

**PERO** hay dos problemas:
1. Si `enrich_brand_failed` (error 204), el pipeline continúa sin `brand_id` → sin `brand_context` → sin `logo_analysis`. El `product_analysis` solo se carga si `draft_id` está presente Y el draft tiene `selected_product_ids`.
2. Aun cuando `vision_analysis` se use en el prompt de copy, **la imagen del producto (`image_url`) nunca se descarga para pasarla a Flux como referencia**. El análisis textual dice "es una botella de tequila con cara sonriente" pero Flux nunca recibe la foto real.

---

## DIAGNÓSTICO FINAL — Hipótesis ordenadas por probabilidad

### 🔴 H1. `product_images` llega vacío desde el frontend (PROBABILIDAD: MUY ALTA)

**Evidencia:**
- `SmartBatchRenderRequest.product_images` espera **base64 strings** del frontend (`app/schemas/post.py:142`)
- El frontend probablemente tiene las imágenes de producto como URLs en `brand_products.image_url`, no como base64
- **No existe código backend que lea `brand_products.image_url` y lo convierta a base64 para inyectarlo en `product_images`**
- Si `product_images = []`: Flux Pro 1.1 (text-to-image) sin referencia → imágenes genéricas sin el producto
- Si `product_images = []`: Nano Banana **nunca se ejecuta** → ni logo ni texto aparecen

**Impacto:** Explica 3 de los 4 síntomas (producto no aparece, logo no aparece, texto no aparece).

### 🔴 H2. Nano Banana se salta cuando no hay `product_images`, incluso con toggles ON (PROBABILIDAD: ALTA)

**Evidencia:** `app/services/post_pipeline.py` líneas 192–244. El bloque Nano Banana está **anidado dentro del `if product_image_urls:`**. El branch `else` (sin product images) **nunca llama a Nano Banana**, sin importar el estado de `include_logo_in_image` ni `include_text_in_image`.

**Esto es un BUG claro:** el Nano Banana debería ejecutarse en ambos branches si los toggles están activos.

### 🟡 H3. Los colores del brand no se propagan al prompt de imagen (PROBABILIDAD: ALTA)

**Evidencia:**
- Los colores se pasan al `CONTENT_PROMPT` para que el LLM los considere al generar `image_prompt`
- Pero el `CONTENT_PROMPT` NO tiene instrucción explícita de "usar estos colores en la escena del image_prompt"
- El `optimize_image_prompt()` en `prompt_optimizer.py` recibe `brand_context` pero solo lee `name` y `tone` — `primary_color`, `secondary_color`, `accent_color` se ignoran completamente (líneas 78–79)
- Resultado: Flux no tiene información de paleta → genera con colores arbitrarios

### 🟡 H4. `enrich_brand_failed` (204) dejó el pipeline sin contexto de brand/producto (PROBABILIDAD: MEDIA-ALTA)

**Evidencia:**
- Log: `enrich_brand_failed error={'message': 'Missing response', 'code': '204'}`
- El `maybe_single()` devuelve 204 cuando no hay filas → el brand_id no matcheó en la tabla `brands`
- El try/except captura la excepción y continúa con `brand_context = {}` (línea 293)
- Resultado: `CONTENT_PROMPT` recibe `"no analizado"` en TODOS los campos del brand y del producto
- El LLM no sabe qué producto es, qué colores tiene, ni cómo se ve → genera prompts genéricos

**Posible causa raíz:** El `brand_id` en el draft no coincide con un registro en `brands`, o el draft no tiene `brand_id`.

### 🟡 H5. El `brand_dict` para imagen no incluye `name` ni `tone` (PROBABILIDAD: MEDIA)

**Evidencia:** `app/services/post_pipeline.py` líneas 367–372:

```python
brand_dict = {
    "logo_b64": payload.brand.logo_b64,
    "primary_color": payload.brand.primary_color,
    "secondary_color": payload.brand.secondary_color,
    "accent_color": payload.brand.accent_color,
}
```

Este dict se pasa a `optimize_image_prompt(brand_context=brand)`, que intenta leer `brand.get('name')` → `None` → default `"Unknown"`, y `brand.get('tone')` → `None` → default `"professional"`.

Resultado: el optimizer no personaliza el prompt para la marca.

---

## Resumen ejecutivo

| Síntoma | Causa raíz |
|---|---|
| Producto no aparece en imagen | H1: `product_images=[]` → Flux text-to-image sin referencia |
| Logo no aparece | H1+H2: sin product images → Nano Banana no se ejecuta |
| Texto/CTA no aparece | H1+H2: sin product images → Nano Banana no se ejecuta |
| Colores del brand ignorados | H3: el optimizer ignora colores + H4: enrich falló → "no analizado" |

**El fix debe abordar:**
1. Backend debe leer `brand_products.image_url` de la DB cuando `product_images` está vacío
2. Mover Nano Banana fuera del block `if product_image_urls:` para que se ejecute en ambos branches
3. Propagar colores del brand al prompt optimizer y/o al prompt de Flux
4. Investigar por qué `enrich_brand_failed` con 204 para el brand_id dado
5. Incluir `name` y `tone` en el `brand_dict` que se pasa al optimizer
