-- Sprint UX-1 fix: scope channel uniqueness to agency level
-- The CM-1 constraint was global (platform, page_id) which prevents
-- different agencies from connecting the same Facebook page.
-- Replace with per-agency constraint: (agency_id, platform, page_id).

-- Drop the old global constraint (name may vary — try both forms)
ALTER TABLE channels
  DROP CONSTRAINT IF EXISTS idx_channels_platform_page_unique;

ALTER TABLE channels
  DROP CONSTRAINT IF EXISTS channels_platform_page_id_key;

-- Also drop any matching unique index
DROP INDEX IF EXISTS idx_channels_platform_page_unique;

-- Add per-agency scoped unique constraint
ALTER TABLE channels
  ADD CONSTRAINT channels_agency_platform_page_unique
  UNIQUE (agency_id, platform, page_id);
