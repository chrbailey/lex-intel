-- ============================================================
-- Personal Knowledge Layer — Expected Value Engine
-- One table. EV-scored. Testable. Cross-platform via MCP.
-- ============================================================

-- Enums
CREATE TYPE knowledge_type AS ENUM (
  'fact', 'decision', 'pattern', 'lesson', 'preference', 'context'
);

CREATE TYPE test_result AS ENUM (
  'untested', 'confirmed', 'contradicted', 'superseded'
);

-- Knowledge table
CREATE TABLE IF NOT EXISTS knowledge (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  content         text NOT NULL,
  knowledge_type  knowledge_type NOT NULL DEFAULT 'fact',
  domain          text NOT NULL DEFAULT 'general',
  confidence      float NOT NULL DEFAULT 0.5
                    CHECK (confidence >= 0 AND confidence <= 1),
  impact          float NOT NULL DEFAULT 0.5
                    CHECK (impact >= 0 AND impact <= 1),
  source          text NOT NULL DEFAULT 'manual',
  source_ref      jsonb DEFAULT '{}',
  embedding       extensions.vector(1536),
  expected_value  float GENERATED ALWAYS AS (confidence * impact) STORED,
  test_result     test_result NOT NULL DEFAULT 'untested',
  tested_at       timestamptz,
  superseded_by   uuid REFERENCES knowledge(id),
  ttl_days        integer,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Performance indexes
CREATE INDEX idx_knowledge_ev ON knowledge(expected_value DESC);
CREATE INDEX idx_knowledge_domain ON knowledge(domain);
CREATE INDEX idx_knowledge_type ON knowledge(knowledge_type);
CREATE INDEX idx_knowledge_test_result ON knowledge(test_result);
CREATE INDEX idx_knowledge_ttl ON knowledge(created_at)
  WHERE ttl_days IS NOT NULL;

-- HNSW vector index (works well even with small datasets)
CREATE INDEX idx_knowledge_embedding ON knowledge
  USING hnsw (embedding extensions.vector_cosine_ops);

-- Auto-update updated_at on any row change
CREATE OR REPLACE FUNCTION update_knowledge_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER knowledge_updated_at
  BEFORE UPDATE ON knowledge
  FOR EACH ROW
  EXECUTE FUNCTION update_knowledge_updated_at();

-- Vector similarity search function (called via supabase.rpc)
CREATE OR REPLACE FUNCTION match_knowledge(
  query_embedding extensions.vector(1536),
  match_threshold float DEFAULT 0.3,
  match_count int DEFAULT 10,
  filter_domain text DEFAULT NULL,
  filter_type text DEFAULT NULL,
  include_contradicted boolean DEFAULT false
)
RETURNS TABLE (
  id uuid,
  content text,
  knowledge_type knowledge_type,
  domain text,
  confidence float,
  impact float,
  expected_value float,
  test_result test_result,
  source text,
  source_ref jsonb,
  ttl_days integer,
  created_at timestamptz,
  updated_at timestamptz,
  similarity float
)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
  RETURN QUERY
  SELECT
    k.id, k.content, k.knowledge_type, k.domain,
    k.confidence, k.impact, k.expected_value,
    k.test_result, k.source, k.source_ref,
    k.ttl_days, k.created_at, k.updated_at,
    1 - (k.embedding <=> query_embedding) as similarity
  FROM knowledge k
  WHERE
    (include_contradicted OR k.test_result != 'contradicted')
    AND (filter_domain IS NULL OR k.domain = filter_domain)
    AND (filter_type IS NULL OR k.knowledge_type = filter_type::knowledge_type)
    AND (k.ttl_days IS NULL OR k.created_at + (k.ttl_days || ' days')::interval > now())
    AND k.embedding IS NOT NULL
    AND 1 - (k.embedding <=> query_embedding) > match_threshold
  ORDER BY k.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- RLS
ALTER TABLE knowledge ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON knowledge
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Anon read access" ON knowledge
  FOR SELECT USING (true);
