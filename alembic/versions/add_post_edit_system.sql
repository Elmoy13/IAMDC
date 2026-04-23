-- Migration: Post edit system — versions, chat history, base image tracking
-- Run this in the Supabase SQL editor

-- 1. Post versions table
CREATE TABLE post_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id UUID REFERENCES generated_posts(id) ON DELETE CASCADE,
  version_number INTEGER NOT NULL,

  -- Snapshot of the post at this version
  headline TEXT,
  body TEXT,
  cta TEXT,
  image_prompt TEXT,
  rendered_image_url TEXT,
  base_image_url TEXT,

  -- Edit context
  user_message TEXT,
  ai_response TEXT,
  change_scope TEXT,

  is_current BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_post_versions_post_id ON post_versions(post_id);
CREATE INDEX idx_post_versions_current ON post_versions(post_id, is_current);

-- 2. Post edit chat table
CREATE TABLE post_edit_chat (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id UUID REFERENCES generated_posts(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  version_id UUID REFERENCES post_versions(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_post_edit_chat_post_id ON post_edit_chat(post_id, created_at);

-- 3. Add base_image_url and edit tracking to generated_posts
ALTER TABLE generated_posts ADD COLUMN IF NOT EXISTS base_image_url TEXT;
ALTER TABLE generated_posts ADD COLUMN IF NOT EXISTS current_version_number INTEGER DEFAULT 1;
ALTER TABLE generated_posts ADD COLUMN IF NOT EXISTS edit_status TEXT DEFAULT 'idle';
