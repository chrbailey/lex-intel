-- ============================================================
-- Lex Intel: Multi-Agent Orchestration Schema
-- Migration 002 — adds pgvector support, agent tables, and
-- vector search functions for the multi-agent pipeline.
--
-- Agents:
--   Scout      → research_items     (discovery & ingestion)
--   Analyst    → analysis_reports   (pattern recognition)
--   Strategist → opportunities      (opportunity identification)
--   Synthesizer→ synthesis_reports  (cross-domain synthesis)
--   Executor   → action_items       (task execution & delivery)
--   Email      → email_triage       (email classification & response)
--   (shared)   → agent_runs         (run logging for all agents)
--
-- Vector search uses pgvector IVFFlat indexes and cosine distance
-- (<=>) for similarity matching across articles and research_items.
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. Enable pgvector extension
-- ────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

-- ────────────────────────────────────────────────────────────
-- 2. Add embedding column to existing articles table
-- ────────────────────────────────────────────────────────────
ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS embedding VECTOR(1536);

-- IVFFlat index for cosine similarity search on articles.
-- lists = 100 is a good starting point; tune after row count > 10K.
-- Note: IVFFlat requires at least some rows to build; Postgres will
-- handle empty-table gracefully but search recall improves with data.
CREATE INDEX IF NOT EXISTS idx_articles_embedding
    ON articles
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ────────────────────────────────────────────────────────────
-- 3. Research items (Scout agent)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS research_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source      TEXT NOT NULL,
    source_url  TEXT,
    title       TEXT NOT NULL,
    body        TEXT,
    category    TEXT,
    relevance   SMALLINT CHECK (relevance BETWEEN 1 AND 5),
    agent_id    TEXT DEFAULT 'scout',
    embedding   VECTOR(1536),
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_items_category
    ON research_items(category);
CREATE INDEX IF NOT EXISTS idx_research_items_relevance
    ON research_items(relevance DESC);
CREATE INDEX IF NOT EXISTS idx_research_items_agent_id
    ON research_items(agent_id);
CREATE INDEX IF NOT EXISTS idx_research_items_created_at
    ON research_items(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_items_embedding
    ON research_items
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ────────────────────────────────────────────────────────────
-- 4. Analysis reports (Analyst agent)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analysis_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type     TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    confidence      REAL CHECK (confidence BETWEEN 0 AND 1),
    source_items    UUID[],
    agent_id        TEXT DEFAULT 'analyst',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analysis_reports_type
    ON analysis_reports(report_type);
CREATE INDEX IF NOT EXISTS idx_analysis_reports_agent_id
    ON analysis_reports(agent_id);
CREATE INDEX IF NOT EXISTS idx_analysis_reports_created_at
    ON analysis_reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_reports_confidence
    ON analysis_reports(confidence DESC);

-- ────────────────────────────────────────────────────────────
-- 5. Opportunities (Strategist agent)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS opportunities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    opp_type        TEXT NOT NULL,
    priority        SMALLINT CHECK (priority BETWEEN 1 AND 5),
    estimated_value TEXT,
    deadline        DATE,
    source_reports  UUID[],
    status          TEXT DEFAULT 'identified',
    agent_id        TEXT DEFAULT 'strategist',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opportunities_status
    ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_priority
    ON opportunities(priority, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_opp_type
    ON opportunities(opp_type);
CREATE INDEX IF NOT EXISTS idx_opportunities_agent_id
    ON opportunities(agent_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_created_at
    ON opportunities(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_deadline
    ON opportunities(deadline)
    WHERE deadline IS NOT NULL;

-- ────────────────────────────────────────────────────────────
-- 6. Synthesis reports (Synthesizer + Guest agents)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS synthesis_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    guest_persona   TEXT,
    novel_ideas     JSONB DEFAULT '[]',
    challenged      JSONB DEFAULT '[]',
    recommendations JSONB DEFAULT '[]',
    source_data     UUID[],
    agent_id        TEXT DEFAULT 'synthesizer',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_synthesis_reports_agent_id
    ON synthesis_reports(agent_id);
CREATE INDEX IF NOT EXISTS idx_synthesis_reports_created_at
    ON synthesis_reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_synthesis_reports_guest_persona
    ON synthesis_reports(guest_persona)
    WHERE guest_persona IS NOT NULL;

-- ────────────────────────────────────────────────────────────
-- 7. Action items (Executor agent)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS action_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    action_type     TEXT NOT NULL,
    priority        SMALLINT CHECK (priority BETWEEN 1 AND 5),
    status          TEXT DEFAULT 'pending',
    deadline        DATE,
    deliverable     TEXT,
    source_reports  UUID[],
    output          JSONB DEFAULT '{}',
    requires_human  BOOLEAN DEFAULT FALSE,
    agent_id        TEXT DEFAULT 'executor',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_action_items_status
    ON action_items(status);
CREATE INDEX IF NOT EXISTS idx_action_items_priority
    ON action_items(priority, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_items_action_type
    ON action_items(action_type);
CREATE INDEX IF NOT EXISTS idx_action_items_agent_id
    ON action_items(agent_id);
CREATE INDEX IF NOT EXISTS idx_action_items_created_at
    ON action_items(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_items_deadline
    ON action_items(deadline)
    WHERE deadline IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_action_items_requires_human
    ON action_items(requires_human)
    WHERE requires_human = TRUE;

-- ────────────────────────────────────────────────────────────
-- 8. Agent run log (all agents)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT NOT NULL,
    run_type        TEXT DEFAULT 'scheduled',
    status          TEXT NOT NULL,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    duration_s      REAL,
    items_processed INTEGER DEFAULT 0,
    items_created   INTEGER DEFAULT 0,
    error           TEXT,
    metadata        JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_id
    ON agent_runs(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status
    ON agent_runs(status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_started_at
    ON agent_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_status
    ON agent_runs(agent_id, status);

-- ────────────────────────────────────────────────────────────
-- 9. Email triage (Email agent)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS email_triage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gmail_id        TEXT NOT NULL,
    from_addr       TEXT NOT NULL,
    from_name       TEXT,
    subject         TEXT NOT NULL,
    received_at     TIMESTAMPTZ,
    triage_action   TEXT NOT NULL,
    category        TEXT,
    priority        SMALLINT CHECK (priority BETWEEN 1 AND 5),
    draft_response  TEXT,
    personal_note   TEXT,
    requires_human  BOOLEAN DEFAULT FALSE,
    status          TEXT DEFAULT 'triaged',
    agent_id        TEXT DEFAULT 'email',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_triage_gmail_id
    ON email_triage(gmail_id);
CREATE INDEX IF NOT EXISTS idx_email_triage_status
    ON email_triage(status);
CREATE INDEX IF NOT EXISTS idx_email_triage_priority
    ON email_triage(priority, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_triage_triage_action
    ON email_triage(triage_action);
CREATE INDEX IF NOT EXISTS idx_email_triage_agent_id
    ON email_triage(agent_id);
CREATE INDEX IF NOT EXISTS idx_email_triage_created_at
    ON email_triage(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_triage_requires_human
    ON email_triage(requires_human)
    WHERE requires_human = TRUE;
CREATE INDEX IF NOT EXISTS idx_email_triage_received_at
    ON email_triage(received_at DESC);

-- ────────────────────────────────────────────────────────────
-- 10. Vector search functions (pgvector RPC)
-- ────────────────────────────────────────────────────────────

-- Match articles by embedding similarity.
-- Called via Supabase RPC: client.rpc("match_articles", {...})
CREATE OR REPLACE FUNCTION match_articles(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.5,
    match_count INT DEFAULT 10,
    filter_days INT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    source TEXT,
    english_title TEXT,
    category TEXT,
    relevance SMALLINT,
    published_at TIMESTAMPTZ,
    similarity FLOAT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id,
        a.source,
        a.english_title,
        a.category,
        a.relevance,
        a.published_at,
        1 - (a.embedding <=> query_embedding) AS similarity
    FROM articles a
    WHERE a.embedding IS NOT NULL
      AND 1 - (a.embedding <=> query_embedding) > match_threshold
      AND (filter_days IS NULL OR a.scraped_at >= NOW() - (filter_days || ' days')::INTERVAL)
    ORDER BY a.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Match research items by embedding similarity.
-- Called via Supabase RPC: client.rpc("match_research_items", {...})
CREATE OR REPLACE FUNCTION match_research_items(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.5,
    match_count INT DEFAULT 10,
    filter_days INT DEFAULT NULL,
    filter_category TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    source TEXT,
    title TEXT,
    category TEXT,
    relevance SMALLINT,
    body TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id,
        r.source,
        r.title,
        r.category,
        r.relevance,
        r.body,
        1 - (r.embedding <=> query_embedding) AS similarity
    FROM research_items r
    WHERE r.embedding IS NOT NULL
      AND 1 - (r.embedding <=> query_embedding) > match_threshold
      AND (filter_days IS NULL OR r.created_at >= NOW() - (filter_days || ' days')::INTERVAL)
      AND (filter_category IS NULL OR r.category = filter_category)
    ORDER BY r.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
