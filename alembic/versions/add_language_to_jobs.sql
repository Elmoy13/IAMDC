-- Migration: Add language column to generation_jobs
-- Run this in the Supabase SQL editor

ALTER TABLE generation_jobs
ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'es';

-- Constrain to valid values
ALTER TABLE generation_jobs
ADD CONSTRAINT generation_jobs_language_check
CHECK (language IN ('es', 'en'));
