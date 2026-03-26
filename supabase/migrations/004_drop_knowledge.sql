-- ============================================================
-- Drop Personal Knowledge Layer — replaced by local SQLite
-- knowledge-store plugin at /Volumes/OWC drive/Knowledge/knowledge.db
-- Applied 2026-03-25
-- ============================================================

-- Remove pg_cron jobs
SELECT cron.unschedule('knowledge-ttl-cleanup');
SELECT cron.unschedule('knowledge-stale-flag');
SELECT cron.unschedule('knowledge-superseded-cleanup');
SELECT cron.unschedule('knowledge-weekly-synthesis');

-- Drop table first (CASCADE removes trigger + indexes)
DROP TABLE IF EXISTS knowledge CASCADE;

-- Now safe to drop functions and types
DROP FUNCTION IF EXISTS match_knowledge;
DROP FUNCTION IF EXISTS update_knowledge_updated_at;
DROP TYPE IF EXISTS knowledge_type;
DROP TYPE IF EXISTS test_result;
