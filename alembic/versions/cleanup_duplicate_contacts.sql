-- Sprint UX-1 fix: clean up duplicate contacts
-- Keeps the oldest contact per (agency_id, platform, platform_user_id) group.
-- Run in Supabase BEFORE deploying the UNIQUE constraint.

-- Step 1: Informational — show duplicates (optional, run manually)
-- SELECT agency_id, platform, platform_user_id, COUNT(*) as duplicates
-- FROM contacts
-- GROUP BY agency_id, platform, platform_user_id
-- HAVING COUNT(*) > 1;

-- Step 2: Reassign conversations from duplicate contacts to the original (oldest)
WITH ranked_contacts AS (
  SELECT
    id,
    agency_id,
    platform,
    platform_user_id,
    ROW_NUMBER() OVER (
      PARTITION BY agency_id, platform, platform_user_id
      ORDER BY created_at ASC
    ) AS rn
  FROM contacts
),
originals AS (
  SELECT id, agency_id, platform, platform_user_id
  FROM ranked_contacts WHERE rn = 1
),
duplicates AS (
  SELECT
    rc.id   AS duplicate_id,
    o.id    AS original_id
  FROM ranked_contacts rc
  JOIN originals o
    ON  o.agency_id        = rc.agency_id
    AND o.platform         = rc.platform
    AND o.platform_user_id = rc.platform_user_id
  WHERE rc.rn > 1
)
UPDATE conversations
SET contact_id = duplicates.original_id
FROM duplicates
WHERE conversations.contact_id = duplicates.duplicate_id;

-- Step 3: Delete the duplicate contacts (no longer referenced by conversations)
DELETE FROM contacts WHERE id IN (
  SELECT rc.id FROM (
    SELECT
      id,
      ROW_NUMBER() OVER (
        PARTITION BY agency_id, platform, platform_user_id
        ORDER BY created_at ASC
      ) AS rn
    FROM contacts
  ) rc WHERE rc.rn > 1
);

-- Step 4: Prevent future duplicates
ALTER TABLE contacts
  ADD CONSTRAINT contacts_agency_platform_user_unique
  UNIQUE (agency_id, platform, platform_user_id);
