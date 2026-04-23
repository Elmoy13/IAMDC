-- Sprint UX-1: Conversations UX fields
-- Run this migration in Supabase BEFORE deploying the new code.

-- Field to mark "last read" by the human agent (for unread count)
ALTER TABLE conversations 
  ADD COLUMN IF NOT EXISTS last_read_at TIMESTAMPTZ;

-- Profile picture for contacts (enriched via Graph API)
ALTER TABLE contacts 
  ADD COLUMN IF NOT EXISTS profile_picture_url TEXT;

-- Tags for intent detection by AI (compra, queja, soporte, etc.)
ALTER TABLE conversations 
  ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'::JSONB;

-- Index for listing conversations by agency + status ordered by last message
CREATE INDEX IF NOT EXISTS idx_conversations_agency_status_last_msg
  ON conversations(agency_id, status, last_message_at DESC NULLS LAST);

NOTIFY pgrst, 'reload schema';
