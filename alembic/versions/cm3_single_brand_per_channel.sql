-- =============================================================================
-- Sprint CM-3: Canales scoped a UNA marca (revertir CM-2.5 multi-brand)
-- =============================================================================
-- INSTRUCCIONES:
--   1. Correr las secciones en orden.
--   2. Revisar los SELECTs intermedios antes de continuar.
--   3. NO correr el DROP TABLE hasta confirmar que el backfill es correcto.
-- =============================================================================

-- ─── 1. Agregar brand_id a channels (nullable al inicio) ────────────────────
ALTER TABLE channels ADD COLUMN brand_id UUID REFERENCES brands(id);

-- ─── 2. Backfill: tomar la primera marca de channel_brands ──────────────────
UPDATE channels c
SET brand_id = (
  SELECT cb.brand_id
  FROM channel_brands cb
  WHERE cb.channel_id = c.id
  ORDER BY cb.is_primary DESC, cb.priority ASC, cb.created_at ASC
  LIMIT 1
)
WHERE c.brand_id IS NULL;

-- ─── 3. Reportar canales huérfanos (sin brand en channel_brands) ────────────
-- REVISAR RESULTADO ANTES DE CONTINUAR
SELECT c.id, c.agency_id, c.platform, c.page_id
FROM channels c
WHERE c.brand_id IS NULL;

-- ─── 4. Reportar canales que tenían MÚLTIPLES marcas en channel_brands ──────
-- (info que se pierde al simplificar a 1:1)
SELECT cb.channel_id, COUNT(*) AS brand_count,
       string_agg(cb.brand_id::text, ', ' ORDER BY cb.is_primary DESC, cb.priority ASC) AS brands
FROM channel_brands cb
GROUP BY cb.channel_id
HAVING COUNT(*) > 1;

-- ─── 5. Backup completo de channel_brands antes de dropear ──────────────────
SELECT * FROM channel_brands;

-- ─── 6. Hacer brand_id NOT NULL (solo cuando TODOS los canales tengan brand_id)
ALTER TABLE channels ALTER COLUMN brand_id SET NOT NULL;

-- ─── 7. Cambiar constraint UNIQUE ───────────────────────────────────────────
-- El viejo constraint era (agency_id, platform, page_id) — ahora lo movemos a
-- (brand_id, platform, page_id) para permitir la misma page en distintas marcas
ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_agency_platform_page_unique;
ALTER TABLE channels ADD CONSTRAINT channels_brand_platform_page_unique
  UNIQUE (brand_id, platform, page_id);

-- ─── 8. Dropear tabla channel_brands ────────────────────────────────────────
DROP TABLE IF EXISTS channel_brands;

-- ─── 9. Limpiar active_brand_id de conversations ───────────────────────────
ALTER TABLE conversations DROP COLUMN IF EXISTS active_brand_id;
