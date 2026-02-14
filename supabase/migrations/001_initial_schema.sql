-- Lex: AI Content Orchestrator — Supabase Schema
-- Replaces Ahgen's JSON file persistence with proper tables.

-- ============================================================
-- SCRAPE_RUNS — metadata per scrape cycle (must be first — referenced by articles)
-- Replaces: state.json → health + last_scrape + pending_count
-- ============================================================
create table if not exists scrape_runs (
  id              uuid primary key default gen_random_uuid(),
  started_at      timestamptz not null default now(),
  finished_at     timestamptz,
  duration_s      real,
  mode            text not null default 'scrape',     -- scrape, analyze, full_cycle
  articles_found  int default 0,
  articles_new    int default 0,                      -- after dedup
  sources_ok      text[],                             -- which scrapers succeeded
  sources_failed  text[],                             -- which scrapers failed
  error           text,

  created_at      timestamptz not null default now()
);

-- ============================================================
-- ARTICLES — scraped content from all sources
-- Replaces: pending.json → articles array
-- ============================================================
create table if not exists articles (
  id            uuid primary key default gen_random_uuid(),
  source        text not null,                        -- e.g. '36kr', 'huxiu', 'gmail'
  source_id     text,                                 -- original ID from source (gmail msg id, url hash)
  title         text not null,
  title_norm    text,                                 -- normalized for dedup (lowercase, no punct)
  url           text,
  body          text,                                 -- raw content (truncated to 10K)
  published_at  timestamptz,                          -- when source published it
  scraped_at    timestamptz not null default now(),    -- when we fetched it

  -- Stage 1 enrichment (filled by analyze pipeline)
  english_title text,
  category      text,                                 -- funding, m_and_a, product, regulation, etc.
  relevance     smallint,                             -- 1-5 score

  -- Lifecycle
  status        text not null default 'pending',      -- pending → analyzed → published → archived
  scrape_run_id uuid references scrape_runs(id),

  created_at    timestamptz not null default now()
);

create index idx_articles_status on articles(status);
create index idx_articles_source on articles(source);
create index idx_articles_scraped_at on articles(scraped_at desc);
create index idx_articles_title_norm on articles(title_norm);

-- ============================================================
-- BRIEFINGS — generated morning briefings
-- Replaces: drafts/ markdown files
-- ============================================================
create table if not exists briefings (
  id              uuid primary key default gen_random_uuid(),
  briefing_text   text not null,                      -- LEAD/PATTERNS/SIGNALS/WATCHLIST/DATA markdown
  article_count   int not null default 0,             -- how many articles went in
  model_used      text,                               -- claude-sonnet-4-20250514, etc.
  scrape_run_id   uuid references scrape_runs(id),

  -- Delivery tracking
  email_sent      boolean not null default false,
  email_sent_at   timestamptz,

  created_at      timestamptz not null default now()
);

-- ============================================================
-- PUBLISH_QUEUE — multi-platform publishing pipeline
-- New table: LinkedIn, Dev.to, Medium post management
--
-- Lifecycle: queued → publishing → published | failed → retry_queued → ...
-- "Always publish" resilience: fallback_body ensures something goes out
-- even if the full analysis pipeline fails. Priority drains HIGH urgency first.
-- ============================================================
create table if not exists publish_queue (
  id              uuid primary key default gen_random_uuid(),
  briefing_id     uuid references briefings(id),
  article_id      uuid references articles(id),       -- source article (nullable for briefing-only posts)

  -- Content
  platform        text not null,                      -- linkedin, devto, medium
  title           text,                               -- post title (Dev.to, Medium)
  body            text not null,                      -- post content
  urgency         text default 'medium',              -- high, medium, low
  language        text default 'en',                  -- en, zh

  -- Publish lifecycle
  status          text not null default 'queued',     -- queued, publishing, published, failed, retry_queued, skipped
  priority        smallint not null default 2,        -- 1=high, 2=medium, 3=low (maps to urgency)
  fallback_body   text,                               -- simpler version (just LEAD paragraph) if full post fails
  max_retries     smallint not null default 3,
  retry_count     int not null default 0,
  next_retry_at   timestamptz,                        -- null = immediate; set for exponential backoff
  publish_log     jsonb not null default '[]'::jsonb,  -- [{at, status, error, platform_response}]
  published_at    timestamptz,
  platform_id     text,                               -- ID returned by platform API after publish
  error           text,                               -- latest error (summary)

  created_at      timestamptz not null default now()
);

create index idx_publish_queue_status on publish_queue(status);
create index idx_publish_queue_platform on publish_queue(platform, status);
create index idx_publish_queue_priority on publish_queue(priority, created_at);
create index idx_publish_queue_retry on publish_queue(next_retry_at) where status = 'retry_queued';

-- ============================================================
-- DEDUP_TITLES — rolling title window for cross-run deduplication
-- Replaces: state.json → recent_titles (500-item window)
-- ============================================================
create table if not exists dedup_titles (
  id          uuid primary key default gen_random_uuid(),
  title_norm  text not null,
  source      text,
  seen_at     timestamptz not null default now()
);

create index idx_dedup_titles_norm on dedup_titles(title_norm);
create index idx_dedup_titles_seen on dedup_titles(seen_at desc);
