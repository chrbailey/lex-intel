-- ============================================================
-- Knowledge Layer — Automated Maintenance via pg_cron
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

-- 1. Daily: Delete expired entries (past TTL)
SELECT cron.schedule(
  'knowledge-ttl-cleanup',
  '0 3 * * *',
  $$
  DELETE FROM knowledge
  WHERE ttl_days IS NOT NULL
    AND created_at + (ttl_days || ' days')::interval < now();
  $$
);

-- 2. Daily: Flag stale untested entries (> 90 days old)
SELECT cron.schedule(
  'knowledge-stale-flag',
  '0 4 * * *',
  $$
  UPDATE knowledge
  SET source_ref = source_ref || '{"needs_review": true}'::jsonb
  WHERE test_result = 'untested'
    AND created_at < now() - interval '90 days'
    AND NOT (source_ref ? 'needs_review');
  $$
);

-- 3. Weekly: Clean up superseded entries older than 6 months
SELECT cron.schedule(
  'knowledge-superseded-cleanup',
  '0 5 * * 0',
  $$
  DELETE FROM knowledge
  WHERE test_result = 'superseded'
    AND superseded_by IS NOT NULL
    AND updated_at < now() - interval '180 days';
  $$
);

-- 4. Weekly: Auto-promote insights to knowledge via Edge Function
SELECT cron.schedule(
  'knowledge-weekly-synthesis',
  '0 6 * * 0',
  $$
  SELECT extensions.http_post(
    'https://pgqoqhozxqpjnukjbzug.supabase.co/functions/v1/knowledge-mcp'::text,
    '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"synthesize","arguments":{"min_confidence":0.7,"dry_run":false}}}'::text,
    'application/json'::text
  );
  $$
);
