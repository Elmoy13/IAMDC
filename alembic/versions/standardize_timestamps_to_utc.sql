-- Standardize ALL timestamp columns to TIMESTAMPTZ (aware UTC).
-- Run in Supabase BEFORE deploying the updated models.

-- messages.sent_at
ALTER TABLE messages
  ALTER COLUMN sent_at TYPE TIMESTAMPTZ
  USING sent_at AT TIME ZONE 'UTC';

-- conversations.last_message_at
ALTER TABLE conversations
  ALTER COLUMN last_message_at TYPE TIMESTAMPTZ
  USING last_message_at AT TIME ZONE 'UTC';

-- conversations.last_read_at
ALTER TABLE conversations
  ALTER COLUMN last_read_at TYPE TIMESTAMPTZ
  USING last_read_at AT TIME ZONE 'UTC';

-- channels.created_at
ALTER TABLE channels
  ALTER COLUMN created_at TYPE TIMESTAMPTZ
  USING created_at AT TIME ZONE 'UTC';

-- channel_brands.created_at
ALTER TABLE channel_brands
  ALTER COLUMN created_at TYPE TIMESTAMPTZ
  USING created_at AT TIME ZONE 'UTC';

-- contacts.created_at
ALTER TABLE contacts
  ALTER COLUMN created_at TYPE TIMESTAMPTZ
  USING created_at AT TIME ZONE 'UTC';
