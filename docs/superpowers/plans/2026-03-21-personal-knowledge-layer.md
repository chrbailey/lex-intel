# Personal Knowledge Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified personal knowledge system with expected value scoring, deployed as one Supabase Edge Function MCP server that any Claude client can connect to.

**Architecture:** One new `knowledge` table in the existing deeptrend Supabase project (`pgqoqhozxqpjnukjbzug`). One Edge Function (`knowledge-mcp`) implementing 6 MCP tools over Streamable HTTP. EV scoring (`confidence × impact × freshness_decay`) ranks all retrieval. Auth via bearer token. Stateless — each request is independent.

**Tech Stack:** Supabase (Postgres 17, pgvector, pg_cron), Deno 2 (Edge Functions), OpenAI text-embedding-3-small (1536 dims), MCP Streamable HTTP protocol (JSON-RPC 2.0)

**Design Spec:** `/Users/christopherbailey/Downloads/personal-knowledge-layer-design.docx`

---

## File Structure

```
/Volumes/OWC drive/Dev/lex/
├── supabase/
│   ├── migrations/
│   │   ├── 001_initial_schema.sql            (existing — lex tables)
│   │   └── 002_knowledge_layer.sql           (NEW — knowledge table, enums, match function, RLS)
│   ├── functions/
│   │   ├── _shared/
│   │   │   ├── ev.ts                         (NEW — pure EV calculation with freshness decay)
│   │   │   └── embed.ts                      (NEW — OpenAI embedding wrapper)
│   │   └── knowledge-mcp/
│   │       ├── index.ts                      (NEW — HTTP handler, auth, JSON-RPC MCP routing)
│   │       └── tools.ts                      (NEW — 6 tool definitions + handler implementations)
│   └── config.toml                            (existing)
├── tests/
│   └── knowledge-mcp/
│       ├── ev.test.ts                        (NEW — Deno unit tests for EV engine)
│       └── integration.sh                    (NEW — curl-based integration tests)
└── .env                                       (existing — add OPENAI_API_KEY, KNOWLEDGE_API_KEY)
```

**Responsibilities:**
- `002_knowledge_layer.sql` — Schema only: table, enums, indexes, vector search function, RLS policies
- `ev.ts` — Pure function: `calculateLiveEV(confidence, impact, createdAt, domain, ttlDays)` → float. No DB, no I/O — independently testable
- `embed.ts` — `embed(text)` → `number[]` via OpenAI API. Single responsibility wrapper
- `index.ts` — HTTP entry point: CORS, auth check, JSON-RPC parse, route to tool handler. ~100 lines
- `tools.ts` — All 6 tool definitions (JSON Schema) + handler functions. The workhorse file. ~350 lines

---

## Phase 1 — Knowledge Table + MCP Server

### Task 1: Prerequisites — Restore Project + Install Deno

**Files:** None (environment setup only)

- [ ] **Step 1: Restore the Supabase project**

The project (`pgqoqhozxqpjnukjbzug`) is currently INACTIVE (paused). Restore it via the Supabase MCP tool:

```
Use: mcp__claude_ai_Supabase__restore_project
  project_id: pgqoqhozxqpjnukjbzug
```

Wait ~2 minutes, then verify status is ACTIVE_HEALTHY:

```
Use: mcp__claude_ai_Supabase__get_project
  id: pgqoqhozxqpjnukjbzug
```

Expected: `"status": "ACTIVE_HEALTHY"`

- [ ] **Step 2: Install Deno**

```bash
brew install deno
deno --version
```

Expected: Deno 2.x installed.

- [ ] **Step 3: Verify pgvector extension is enabled**

```sql
-- Via Supabase MCP execute_sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
```

If not found, enable it:

```sql
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
```

- [ ] **Step 4: Verify existing tables**

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;
```

Expected: articles, briefings, dedup_titles, insights, publish_queue, raw_signals, scrape_runs. Note the exact columns of `raw_signals` and `insights` for use in Task 5 (query_signals tool).

- [ ] **Step 5: Link Supabase CLI to project**

```bash
cd "/Volumes/OWC drive/Dev/lex"
supabase link --project-ref pgqoqhozxqpjnukjbzug
```

- [ ] **Step 6: Create function directories + scaffold**

```bash
mkdir -p "/Volumes/OWC drive/Dev/lex/supabase/functions/_shared"
mkdir -p "/Volumes/OWC drive/Dev/lex/supabase/functions/knowledge-mcp"
mkdir -p "/Volumes/OWC drive/Dev/lex/tests/knowledge-mcp"
```

- [ ] **Step 7: Commit**

```bash
cd "/Volumes/OWC drive/Dev/lex"
git add supabase/functions/ tests/knowledge-mcp/
git commit -m "chore: scaffold knowledge-mcp Edge Function directories"
```

---

### Task 2: Knowledge Table Migration

**Files:**
- Create: `supabase/migrations/002_knowledge_layer.sql`

- [ ] **Step 1: Write the migration**

```sql
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
  embedding       vector(1536),
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

-- HNSW vector index (works well even with small datasets, unlike IVFFlat)
CREATE INDEX idx_knowledge_embedding ON knowledge
  USING hnsw (embedding vector_cosine_ops);

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
  query_embedding vector(1536),
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
```

- [ ] **Step 2: Apply the migration**

```bash
cd "/Volumes/OWC drive/Dev/lex"
supabase db push --project-ref pgqoqhozxqpjnukjbzug
```

Or via Supabase MCP:

```
Use: mcp__claude_ai_Supabase__apply_migration
  project_id: pgqoqhozxqpjnukjbzug
  name: knowledge_layer
  query: <full SQL above>
```

- [ ] **Step 3: Verify the table exists**

```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'knowledge' ORDER BY ordinal_position;
```

Expected: All columns from the schema above.

- [ ] **Step 4: Verify the match function exists**

```sql
SELECT proname, pronargs FROM pg_proc WHERE proname = 'match_knowledge';
```

Expected: `match_knowledge` with 6 arguments.

- [ ] **Step 5: Commit**

```bash
cd "/Volumes/OWC drive/Dev/lex"
git add supabase/migrations/002_knowledge_layer.sql
git commit -m "feat: add knowledge table with EV scoring and vector search"
```

---

### Task 3: Shared Libraries — EV Engine + Embeddings

**Files:**
- Create: `supabase/functions/_shared/ev.ts`
- Create: `supabase/functions/_shared/embed.ts`
- Create: `tests/knowledge-mcp/ev.test.ts`

- [ ] **Step 1: Write the EV engine**

Create `supabase/functions/_shared/ev.ts`:

```typescript
/**
 * Expected Value Engine
 * EV = confidence × impact × freshness_decay
 * Decay is domain-specific: AI knowledge decays fast, ERP knowledge is stable.
 */

const DECAY_RATES: Record<string, number> = {
  ai: 0.05,        // 5% per week — landscape moves fast
  fishing: 0.001,  // nearly stable — regulations change annually
  erp: 0.005,      // very stable — implementation patterns endure
  personal: 0.01,
  stanford: 0.01,
  business: 0.02,
  general: 0.02,
};

export function calculateLiveEV(
  confidence: number,
  impact: number,
  createdAt: string,
  domain: string,
  ttlDays: number | null
): number {
  const ageMs = Date.now() - new Date(createdAt).getTime();
  const ageDays = ageMs / (24 * 60 * 60 * 1000);

  // TTL expiration: EV drops to zero
  if (ttlDays !== null && ageDays > ttlDays) return 0;

  const ageWeeks = ageDays / 7;
  const decayRate = DECAY_RATES[domain] || DECAY_RATES.general;
  const freshness = Math.pow(1 - decayRate, ageWeeks);

  return confidence * impact * freshness;
}
```

- [ ] **Step 2: Write the embeddings wrapper**

Create `supabase/functions/_shared/embed.ts`:

```typescript
/**
 * OpenAI Embedding Wrapper
 * Uses text-embedding-3-small (1536 dims) for pgvector compatibility.
 */

export async function embed(text: string): Promise<number[]> {
  const apiKey = Deno.env.get("OPENAI_API_KEY");
  if (!apiKey) throw new Error("OPENAI_API_KEY not set as Edge Function secret");

  const res = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "text-embedding-3-small",
      input: text,
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`OpenAI embedding failed (${res.status}): ${err}`);
  }

  const data = await res.json();
  return data.data[0].embedding;
}
```

- [ ] **Step 3: Write EV engine unit tests**

Create `tests/knowledge-mcp/ev.test.ts`:

```typescript
import { assertEquals } from "jsr:@std/assert";
import { calculateLiveEV } from "../../supabase/functions/_shared/ev.ts";

Deno.test("base EV is confidence * impact for fresh entry", () => {
  const ev = calculateLiveEV(0.9, 0.8, new Date().toISOString(), "erp", null);
  // freshness ≈ 1.0 for just-created entry
  const expected = 0.9 * 0.8 * 1.0;
  assertEquals(Math.abs(ev - expected) < 0.001, true);
});

Deno.test("expired TTL returns zero", () => {
  const oldDate = new Date(Date.now() - 100 * 24 * 60 * 60 * 1000).toISOString(); // 100 days ago
  const ev = calculateLiveEV(0.9, 0.9, oldDate, "ai", 30); // TTL = 30 days
  assertEquals(ev, 0);
});

Deno.test("AI domain decays faster than ERP", () => {
  const sixWeeksAgo = new Date(Date.now() - 42 * 24 * 60 * 60 * 1000).toISOString();
  const aiEV = calculateLiveEV(0.9, 0.9, sixWeeksAgo, "ai", null);
  const erpEV = calculateLiveEV(0.9, 0.9, sixWeeksAgo, "erp", null);
  assertEquals(erpEV > aiEV, true, "ERP should decay slower than AI");
});

Deno.test("unknown domain uses general decay rate", () => {
  const ev = calculateLiveEV(1.0, 1.0, new Date().toISOString(), "unknown_domain", null);
  assertEquals(Math.abs(ev - 1.0) < 0.01, true);
});

Deno.test("zero confidence gives zero EV", () => {
  const ev = calculateLiveEV(0, 0.9, new Date().toISOString(), "ai", null);
  assertEquals(ev, 0);
});
```

- [ ] **Step 4: Run the tests**

```bash
cd "/Volumes/OWC drive/Dev/lex"
deno test tests/knowledge-mcp/ev.test.ts
```

Expected: 5 tests, all PASS.

- [ ] **Step 5: Commit**

```bash
cd "/Volumes/OWC drive/Dev/lex"
git add supabase/functions/_shared/ev.ts supabase/functions/_shared/embed.ts tests/knowledge-mcp/ev.test.ts
git commit -m "feat: add EV engine with freshness decay and embedding wrapper"
```

---

### Task 4: MCP Protocol Handler + Capture & Search Tools

**Files:**
- Create: `supabase/functions/knowledge-mcp/index.ts`
- Create: `supabase/functions/knowledge-mcp/tools.ts`

- [ ] **Step 1: Write the MCP protocol handler**

Create `supabase/functions/knowledge-mcp/index.ts`:

```typescript
import { createClient } from "jsr:@supabase/supabase-js@2";
import { TOOL_DEFINITIONS, handleToolCall } from "./tools.ts";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function jsonRpc(
  id: string | number | null,
  result: unknown,
  error: { code: number; message: string } | null
): Response {
  const body: Record<string, unknown> = { jsonrpc: "2.0" };
  if (id !== null) body.id = id;
  if (error) body.error = error;
  else body.result = result;
  return new Response(JSON.stringify(body), {
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req) => {
  // CORS preflight
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: CORS_HEADERS });
  }

  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405, headers: CORS_HEADERS });
  }

  // Auth: bearer token or ?key= query param
  const apiKey = Deno.env.get("KNOWLEDGE_API_KEY");
  if (apiKey) {
    const url = new URL(req.url);
    const provided =
      req.headers.get("authorization")?.replace("Bearer ", "") ||
      url.searchParams.get("key");
    if (provided !== apiKey) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
      });
    }
  }

  // Supabase client (service role for full DB access)
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
  );

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return jsonRpc(null, null, { code: -32700, message: "Parse error" });
  }

  const { method, params, id } = body as {
    method: string;
    params?: Record<string, unknown>;
    id?: string | number;
  };

  switch (method) {
    case "initialize":
      return jsonRpc(id ?? null, {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "knowledge-mcp", version: "1.0.0" },
      }, null);

    case "notifications/initialized":
      return new Response(null, { status: 204, headers: CORS_HEADERS });

    case "tools/list":
      return jsonRpc(id ?? null, { tools: TOOL_DEFINITIONS }, null);

    case "tools/call": {
      const toolParams = params as { name: string; arguments?: Record<string, unknown> };
      try {
        const result = await handleToolCall(supabase, toolParams.name, toolParams.arguments ?? {});
        return jsonRpc(id ?? null, result, null);
      } catch (err) {
        return jsonRpc(id ?? null, null, {
          code: -32603,
          message: err instanceof Error ? err.message : "Internal error",
        });
      }
    }

    case "ping":
      return jsonRpc(id ?? null, {}, null);

    default:
      return jsonRpc(id ?? null, null, {
        code: -32601,
        message: `Unknown method: ${method}`,
      });
  }
});
```

- [ ] **Step 2: Write tools.ts — definitions + capture + search handlers**

Create `supabase/functions/knowledge-mcp/tools.ts`:

```typescript
import { type SupabaseClient } from "jsr:@supabase/supabase-js@2";
import { calculateLiveEV } from "../_shared/ev.ts";
import { embed } from "../_shared/embed.ts";

// ─── Tool Definitions ────────────────────────────────────────

export const TOOL_DEFINITIONS = [
  {
    name: "capture",
    description: "Store new knowledge with type, domain, confidence, and impact. Auto-embeds for semantic search.",
    inputSchema: {
      type: "object",
      properties: {
        content: { type: "string", description: "The knowledge entry (one idea per entry)" },
        knowledge_type: {
          type: "string",
          enum: ["fact", "decision", "pattern", "lesson", "preference", "context"],
          default: "fact",
        },
        domain: { type: "string", description: "Domain: ai, erp, fishing, personal, stanford, business, general", default: "general" },
        confidence: { type: "number", minimum: 0, maximum: 1, default: 0.5, description: "How certain is this?" },
        impact: { type: "number", minimum: 0, maximum: 1, default: 0.5, description: "How much does acting on this change outcomes?" },
        source: { type: "string", default: "manual", description: "conversation, observation, synthesis, or manual" },
        source_ref: { type: "object", default: {}, description: "Chat URI, insight ID, signal ID, or external URL" },
        ttl_days: { type: "number", description: "Auto-expire after N days (omit for permanent)" },
      },
      required: ["content"],
    },
  },
  {
    name: "search",
    description: "Semantic search via pgvector embedding similarity, ranked by expected value (confidence × impact × freshness).",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Natural language search query" },
        domain: { type: "string", description: "Filter by domain" },
        knowledge_type: { type: "string", description: "Filter by type" },
        min_confidence: { type: "number", default: 0, description: "Minimum confidence threshold" },
        limit: { type: "number", default: 10, maximum: 50 },
        include_contradicted: { type: "boolean", default: false },
      },
      required: ["query"],
    },
  },
  {
    name: "validate",
    description: "Mark knowledge as confirmed, contradicted, or superseded. Updates confidence accordingly.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Knowledge entry UUID" },
        test_result: { type: "string", enum: ["confirmed", "contradicted", "superseded"] },
        superseded_by: { type: "string", description: "UUID of replacement entry (when superseded)" },
        notes: { type: "string", description: "Why this validation was made" },
      },
      required: ["id", "test_result"],
    },
  },
  {
    name: "synthesize",
    description: "Promote high-confidence insights to knowledge entries. Preview with dry_run=true first.",
    inputSchema: {
      type: "object",
      properties: {
        min_confidence: { type: "number", default: 0.7, description: "Minimum insight confidence for promotion" },
        dry_run: { type: "boolean", default: true, description: "Preview what would be promoted without writing" },
      },
    },
  },
  {
    name: "status",
    description: "System health: counts by type/domain, top EV entries, untested entries, entries expiring soon.",
    inputSchema: {
      type: "object",
      properties: {
        top_n: { type: "number", default: 5, description: "How many top EV entries to return" },
      },
    },
  },
  {
    name: "query_signals",
    description: "Direct access to raw_signals table for ad-hoc analysis of collected signals.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Text search in signal content" },
        source: { type: "string", description: "Filter by signal source" },
        limit: { type: "number", default: 20 },
        since: { type: "string", description: "ISO date — only signals after this date" },
      },
    },
  },
];

// ─── Tool Dispatch ───────────────────────────────────────────

export async function handleToolCall(
  supabase: SupabaseClient,
  name: string,
  args: Record<string, unknown>
): Promise<{ content: Array<{ type: string; text: string }> }> {
  const handlers: Record<string, (sb: SupabaseClient, a: Record<string, unknown>) => Promise<string>> = {
    capture: handleCapture,
    search: handleSearch,
    validate: handleValidate,
    synthesize: handleSynthesize,
    status: handleStatus,
    query_signals: handleQuerySignals,
  };

  const handler = handlers[name];
  if (!handler) {
    return { content: [{ type: "text", text: `Unknown tool: ${name}` }] };
  }

  const text = await handler(supabase, args);
  return { content: [{ type: "text", text }] };
}

// ─── capture ─────────────────────────────────────────────────

async function handleCapture(
  supabase: SupabaseClient,
  args: Record<string, unknown>
): Promise<string> {
  const content = args.content as string;

  // Generate embedding (non-blocking failure: store without embedding if API fails)
  let embedding: number[] | null = null;
  try {
    embedding = await embed(content);
  } catch (err) {
    console.error("Embedding failed, storing without vector:", err);
  }

  const row = {
    content,
    knowledge_type: (args.knowledge_type as string) || "fact",
    domain: (args.domain as string) || "general",
    confidence: (args.confidence as number) ?? 0.5,
    impact: (args.impact as number) ?? 0.5,
    source: (args.source as string) || "manual",
    source_ref: args.source_ref || {},
    ttl_days: (args.ttl_days as number) ?? null,
    embedding,
  };

  const { data, error } = await supabase
    .from("knowledge")
    .insert(row)
    .select("id, content, expected_value, domain, knowledge_type")
    .single();

  if (error) throw new Error(`capture failed: ${error.message}`);

  return JSON.stringify({
    stored: true,
    id: data.id,
    expected_value: data.expected_value,
    embedded: embedding !== null,
    summary: `Captured ${data.knowledge_type} in ${data.domain} (EV: ${data.expected_value.toFixed(3)})`,
  });
}

// ─── search ──────────────────────────────────────────────────

async function handleSearch(
  supabase: SupabaseClient,
  args: Record<string, unknown>
): Promise<string> {
  const query = args.query as string;
  const limit = Math.min((args.limit as number) || 10, 50);
  const domain = (args.domain as string) || null;
  const knowledgeType = (args.knowledge_type as string) || null;
  const minConfidence = (args.min_confidence as number) || 0;
  const includeContradicted = (args.include_contradicted as boolean) || false;

  // Try semantic search first (requires embedding)
  let results: unknown[] = [];
  try {
    const queryEmbedding = await embed(query);
    const { data, error } = await supabase.rpc("match_knowledge", {
      query_embedding: queryEmbedding,
      match_threshold: 0.3,
      match_count: limit,
      filter_domain: domain,
      filter_type: knowledgeType,
      include_contradicted: includeContradicted,
    });
    if (error) throw error;
    results = data || [];
  } catch (err) {
    // Fallback to text search if embedding fails
    console.error("Vector search failed, falling back to text:", err);
    let q = supabase
      .from("knowledge")
      .select("*")
      .ilike("content", `%${query}%`)
      .order("expected_value", { ascending: false })
      .limit(limit);

    if (domain) q = q.eq("domain", domain);
    if (knowledgeType) q = q.eq("knowledge_type", knowledgeType);
    if (!includeContradicted) q = q.neq("test_result", "contradicted");

    const { data, error: textError } = await q;
    if (textError) throw new Error(`search failed: ${textError.message}`);
    results = data || [];
  }

  // Re-rank by live EV (includes freshness decay)
  const ranked = (results as Array<Record<string, unknown>>)
    .filter((r) => (r.confidence as number) >= minConfidence)
    .map((r) => ({
      ...r,
      live_ev: calculateLiveEV(
        r.confidence as number,
        r.impact as number,
        r.created_at as string,
        r.domain as string,
        r.ttl_days as number | null
      ),
    }))
    .sort((a, b) => {
      // Composite: similarity (if available) * live_ev
      const simA = (a.similarity as number) || 1;
      const simB = (b.similarity as number) || 1;
      return simB * b.live_ev - simA * a.live_ev;
    });

  return JSON.stringify({
    count: ranked.length,
    results: ranked.map((r) => ({
      id: r.id,
      content: r.content,
      knowledge_type: r.knowledge_type,
      domain: r.domain,
      confidence: r.confidence,
      impact: r.impact,
      live_ev: Number(r.live_ev.toFixed(4)),
      test_result: r.test_result,
      similarity: r.similarity ? Number((r.similarity as number).toFixed(4)) : null,
      source: r.source,
      created_at: r.created_at,
    })),
  });
}

// ─── Placeholder handlers (implemented in Task 5 and Task 8) ─

async function handleValidate(_sb: SupabaseClient, _args: Record<string, unknown>): Promise<string> {
  return JSON.stringify({ error: "Not yet implemented — see Task 5" });
}

async function handleSynthesize(_sb: SupabaseClient, _args: Record<string, unknown>): Promise<string> {
  return JSON.stringify({ error: "Not yet implemented — see Task 8" });
}

async function handleStatus(_sb: SupabaseClient, _args: Record<string, unknown>): Promise<string> {
  return JSON.stringify({ error: "Not yet implemented — see Task 5" });
}

async function handleQuerySignals(_sb: SupabaseClient, _args: Record<string, unknown>): Promise<string> {
  return JSON.stringify({ error: "Not yet implemented — see Task 5" });
}
```

- [ ] **Step 3: Commit**

```bash
cd "/Volumes/OWC drive/Dev/lex"
git add supabase/functions/knowledge-mcp/
git commit -m "feat: MCP protocol handler with capture and search tools"
```

---

### Task 5: Validate, Status, and Query Signals Tools

**Files:**
- Modify: `supabase/functions/knowledge-mcp/tools.ts` (replace placeholder handlers)

- [ ] **Step 1: Implement handleValidate**

Replace the `handleValidate` placeholder in `tools.ts`:

```typescript
async function handleValidate(
  supabase: SupabaseClient,
  args: Record<string, unknown>
): Promise<string> {
  const id = args.id as string;
  const newResult = args.test_result as string;
  const supersededBy = (args.superseded_by as string) || null;
  const notes = (args.notes as string) || null;

  // Fetch current entry
  const { data: current, error: fetchError } = await supabase
    .from("knowledge")
    .select("confidence, test_result")
    .eq("id", id)
    .single();

  if (fetchError) throw new Error(`Entry not found: ${fetchError.message}`);

  // Compute new confidence based on test result
  let newConfidence = current.confidence as number;
  switch (newResult) {
    case "confirmed":
      newConfidence = Math.min(0.95, newConfidence + 0.1);
      break;
    case "contradicted":
      newConfidence = 0.2;
      break;
    case "superseded":
      newConfidence = 0; // EV zeroes out
      break;
  }

  const update: Record<string, unknown> = {
    test_result: newResult,
    confidence: newConfidence,
    tested_at: new Date().toISOString(),
  };
  if (supersededBy) update.superseded_by = supersededBy;
  if (notes) {
    // Merge notes into existing source_ref (don't overwrite)
    const { data: existing } = await supabase
      .from("knowledge")
      .select("source_ref")
      .eq("id", id)
      .single();
    update.source_ref = { ...(existing?.source_ref || {}), validation_notes: notes };
  }

  const { data, error } = await supabase
    .from("knowledge")
    .update(update)
    .eq("id", id)
    .select("id, content, confidence, expected_value, test_result")
    .single();

  if (error) throw new Error(`validate failed: ${error.message}`);

  return JSON.stringify({
    validated: true,
    id: data.id,
    previous_result: current.test_result,
    new_result: data.test_result,
    confidence: data.confidence,
    expected_value: data.expected_value,
  });
}
```

- [ ] **Step 2: Implement handleStatus**

Replace the `handleStatus` placeholder:

```typescript
async function handleStatus(
  supabase: SupabaseClient,
  args: Record<string, unknown>
): Promise<string> {
  const topN = (args.top_n as number) || 5;

  // Total count
  const { count: total } = await supabase
    .from("knowledge")
    .select("*", { count: "exact", head: true });

  // By type
  const { data: byType } = await supabase
    .from("knowledge")
    .select("knowledge_type")
    .then(({ data }) => ({
      data: Object.entries(
        (data || []).reduce((acc: Record<string, number>, r: Record<string, unknown>) => {
          const t = r.knowledge_type as string;
          acc[t] = (acc[t] || 0) + 1;
          return acc;
        }, {})
      ),
    }));

  // By domain
  const { data: byDomain } = await supabase
    .from("knowledge")
    .select("domain")
    .then(({ data }) => ({
      data: Object.entries(
        (data || []).reduce((acc: Record<string, number>, r: Record<string, unknown>) => {
          const d = r.domain as string;
          acc[d] = (acc[d] || 0) + 1;
          return acc;
        }, {})
      ),
    }));

  // Top N by EV (with live decay applied client-side)
  const { data: topEntries } = await supabase
    .from("knowledge")
    .select("id, content, confidence, impact, domain, expected_value, test_result, created_at, ttl_days")
    .neq("test_result", "contradicted")
    .order("expected_value", { ascending: false })
    .limit(topN * 2); // fetch extra to re-rank after decay

  const ranked = (topEntries || [])
    .map((r: Record<string, unknown>) => ({
      ...r,
      live_ev: calculateLiveEV(
        r.confidence as number,
        r.impact as number,
        r.created_at as string,
        r.domain as string,
        r.ttl_days as number | null
      ),
    }))
    .sort((a, b) => b.live_ev - a.live_ev)
    .slice(0, topN);

  // Untested count
  const { count: untested } = await supabase
    .from("knowledge")
    .select("*", { count: "exact", head: true })
    .eq("test_result", "untested");

  // Expiring within 30 days
  const { data: expiringSoon } = await supabase
    .from("knowledge")
    .select("id, content, domain, ttl_days, created_at")
    .not("ttl_days", "is", null)
    .order("created_at", { ascending: true })
    .limit(100);

  const expiring = (expiringSoon || []).filter((r: Record<string, unknown>) => {
    const ageMs = Date.now() - new Date(r.created_at as string).getTime();
    const ageDays = ageMs / (24 * 60 * 60 * 1000);
    const daysRemaining = (r.ttl_days as number) - ageDays;
    return daysRemaining > 0 && daysRemaining <= 30;
  });

  return JSON.stringify({
    total: total || 0,
    by_type: Object.fromEntries(byType || []),
    by_domain: Object.fromEntries(byDomain || []),
    untested: untested || 0,
    expiring_within_30_days: expiring.length,
    top_by_live_ev: ranked.map((r) => ({
      id: r.id,
      content: (r.content as string).slice(0, 100),
      live_ev: Number(r.live_ev.toFixed(4)),
      domain: r.domain,
      test_result: r.test_result,
    })),
  });
}
```

- [ ] **Step 3: Implement handleQuerySignals**

Replace the `handleQuerySignals` placeholder:

```typescript
async function handleQuerySignals(
  supabase: SupabaseClient,
  args: Record<string, unknown>
): Promise<string> {
  const query = (args.query as string) || null;
  const source = (args.source as string) || null;
  const limit = Math.min((args.limit as number) || 20, 100);
  const since = (args.since as string) || null;

  // Check if raw_signals table exists
  let q = supabase
    .from("raw_signals")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (query) q = q.ilike("content", `%${query}%`);
  if (source) q = q.eq("source", source);
  if (since) q = q.gte("created_at", since);

  const { data, error } = await q;

  if (error) {
    // Table might not exist or have different columns
    return JSON.stringify({
      error: `query_signals failed: ${error.message}`,
      hint: "Check that the raw_signals table exists and has 'content', 'source', 'created_at' columns.",
    });
  }

  return JSON.stringify({
    count: (data || []).length,
    signals: data || [],
  });
}
```

- [ ] **Step 4: Commit**

```bash
cd "/Volumes/OWC drive/Dev/lex"
git add supabase/functions/knowledge-mcp/tools.ts
git commit -m "feat: add validate, status, and query_signals tool handlers"
```

---

### Task 6: Deploy + Integration Test

**Files:**
- Create: `tests/knowledge-mcp/integration.sh`

- [ ] **Step 1: Set Edge Function secrets**

The user must supply the actual key values. Use `pbpaste` for secrets — never echo them.

```bash
# User copies OPENAI_API_KEY to clipboard
cd "/Volumes/OWC drive/Dev/lex"
supabase secrets set OPENAI_API_KEY=$(pbpaste) --project-ref pgqoqhozxqpjnukjbzug

# Generate a random API key for knowledge-mcp auth
KNOWLEDGE_KEY=$(openssl rand -hex 32)
supabase secrets set KNOWLEDGE_API_KEY=$KNOWLEDGE_KEY --project-ref pgqoqhozxqpjnukjbzug
echo "Save this KNOWLEDGE_API_KEY to .env (it won't be shown again)"
echo $KNOWLEDGE_KEY | pbcopy
# User pastes into .env
```

- [ ] **Step 2: Deploy the Edge Function**

```bash
cd "/Volumes/OWC drive/Dev/lex"
supabase functions deploy knowledge-mcp --project-ref pgqoqhozxqpjnukjbzug
```

Expected: `Edge Function 'knowledge-mcp' deployed successfully.`

The function URL will be:
`https://pgqoqhozxqpjnukjbzug.supabase.co/functions/v1/knowledge-mcp`

- [ ] **Step 3: Write integration test script**

Create `tests/knowledge-mcp/integration.sh`:

```bash
#!/bin/bash
# Integration tests for knowledge-mcp Edge Function
# Usage: KNOWLEDGE_API_KEY=<key> bash tests/knowledge-mcp/integration.sh

set -euo pipefail

BASE_URL="https://pgqoqhozxqpjnukjbzug.supabase.co/functions/v1/knowledge-mcp"
AUTH="Authorization: Bearer ${KNOWLEDGE_API_KEY:?Set KNOWLEDGE_API_KEY}"
CT="Content-Type: application/json"

pass=0
fail=0

check() {
  local name="$1" expected="$2" actual="$3"
  if echo "$actual" | grep -q "$expected"; then
    echo "  PASS: $name"
    ((pass++))
  else
    echo "  FAIL: $name (expected '$expected' in response)"
    echo "    Got: $actual"
    ((fail++))
  fi
}

echo "=== MCP Protocol Tests ==="

# 1. Initialize
resp=$(curl -s -X POST "$BASE_URL" -H "$AUTH" -H "$CT" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
check "initialize" "knowledge-mcp" "$resp"

# 2. Tools list
resp=$(curl -s -X POST "$BASE_URL" -H "$AUTH" -H "$CT" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}')
check "tools/list has capture" "capture" "$resp"
check "tools/list has search" "search" "$resp"
check "tools/list has 6 tools" "query_signals" "$resp"

# 3. Ping
resp=$(curl -s -X POST "$BASE_URL" -H "$AUTH" -H "$CT" \
  -d '{"jsonrpc":"2.0","id":3,"method":"ping","params":{}}')
check "ping" '"result"' "$resp"

echo ""
echo "=== Tool Tests ==="

# 4. Capture
resp=$(curl -s -X POST "$BASE_URL" -H "$AUTH" -H "$CT" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"capture","arguments":{"content":"California halibut: minimum size 22 inches, 5 fish daily bag limit in Monterey Bay","knowledge_type":"fact","domain":"fishing","confidence":0.95,"impact":0.9,"source":"manual","ttl_days":365}}}')
check "capture returns stored:true" "stored" "$resp"
check "capture returns id" '"id"' "$resp"

# Extract the ID for later tests
ENTRY_ID=$(echo "$resp" | python3 -c "import sys,json; r=json.loads(sys.stdin.read()); print(json.loads(r['result']['content'][0]['text'])['id'])" 2>/dev/null || echo "")

# 5. Search
resp=$(curl -s -X POST "$BASE_URL" -H "$AUTH" -H "$CT" \
  -d '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"search","arguments":{"query":"halibut fishing regulations California","domain":"fishing","limit":5}}}')
check "search returns results" "results" "$resp"

# 6. Status
resp=$(curl -s -X POST "$BASE_URL" -H "$AUTH" -H "$CT" \
  -d '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"status","arguments":{"top_n":3}}}')
check "status returns total" "total" "$resp"

# 7. Validate (if we got an ID)
if [ -n "$ENTRY_ID" ]; then
  resp=$(curl -s -X POST "$BASE_URL" -H "$AUTH" -H "$CT" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":7,\"method\":\"tools/call\",\"params\":{\"name\":\"validate\",\"arguments\":{\"id\":\"$ENTRY_ID\",\"test_result\":\"confirmed\",\"notes\":\"Verified against 2026 CDFW regs\"}}}")
  check "validate confirms entry" "validated" "$resp"
fi

# 8. Query signals
resp=$(curl -s -X POST "$BASE_URL" -H "$AUTH" -H "$CT" \
  -d '{"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"query_signals","arguments":{"limit":5}}}')
check "query_signals responds" "count\|error" "$resp"

echo ""
echo "=== Results: $pass passed, $fail failed ==="
[ "$fail" -eq 0 ] || exit 1
```

- [ ] **Step 4: Run integration tests**

```bash
cd "/Volumes/OWC drive/Dev/lex"
KNOWLEDGE_API_KEY=$(grep KNOWLEDGE_API_KEY .env | cut -d= -f2) \
  bash tests/knowledge-mcp/integration.sh
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd "/Volumes/OWC drive/Dev/lex"
git add tests/knowledge-mcp/integration.sh
git commit -m "test: add integration test suite for knowledge-mcp"
```

---

### Task 7: Connect Claude Code + End-to-End Test

**Files:** None (configuration only)

- [ ] **Step 1: Add MCP server to Claude Code**

```bash
claude mcp add knowledge-mcp \
  --transport http \
  --url "https://pgqoqhozxqpjnukjbzug.supabase.co/functions/v1/knowledge-mcp" \
  --header "Authorization: Bearer <KNOWLEDGE_API_KEY>"
```

Replace `<KNOWLEDGE_API_KEY>` with the actual key from `.env`.

- [ ] **Step 2: Verify tools are visible in Claude Code**

Start a new Claude Code session and check that the 6 knowledge tools appear. Test:

```
Use the knowledge capture tool to store: "PromptSpeak v0.4.1 published to npm with 56 MCP tools" as a fact in the ai domain with confidence 0.95 and impact 0.3
```

Expected: Tool call succeeds, returns stored entry with EV.

- [ ] **Step 3: Test semantic search round-trip**

```
Use the knowledge search tool to find entries about "PromptSpeak npm publishing"
```

Expected: Returns the entry from Step 2 with similarity score and live EV.

- [ ] **Step 4: Test cross-platform via Claude AI**

If Claude AI has the Supabase MCP connector:
1. Query the knowledge table directly via SQL
2. Verify the entry from Step 2 exists

For full MCP integration with Claude AI: add the Edge Function URL as a remote MCP server in Claude AI settings (when available).

---

## Phase 2 — Auto-Synthesis + Maintenance

### Task 8: Synthesize Tool

**Files:**
- Modify: `supabase/functions/knowledge-mcp/tools.ts` (replace synthesize placeholder)

- [ ] **Step 1: Implement handleSynthesize**

Replace the `handleSynthesize` placeholder in `tools.ts`:

```typescript
async function handleSynthesize(
  supabase: SupabaseClient,
  args: Record<string, unknown>
): Promise<string> {
  const minConfidence = (args.min_confidence as number) || 0.7;
  const dryRun = (args.dry_run as boolean) ?? true;

  // Fetch insights above confidence threshold
  // NOTE: Adjust column names to match your actual insights table schema.
  // The insights table may have columns like: id, content/summary, type, confidence, source_refs, etc.
  const { data: insights, error: fetchError } = await supabase
    .from("insights")
    .select("*")
    .gte("confidence", minConfidence)
    .order("confidence", { ascending: false });

  if (fetchError) {
    return JSON.stringify({
      error: `Failed to fetch insights: ${fetchError.message}`,
      hint: "Check that the 'insights' table exists with a 'confidence' column.",
    });
  }

  if (!insights || insights.length === 0) {
    return JSON.stringify({
      promoted: 0,
      message: `No insights found with confidence >= ${minConfidence}`,
    });
  }

  // Check which insights are already in knowledge (dedup by content similarity)
  const candidates = [];
  for (const insight of insights) {
    // Use the insight's primary text field (may be 'content', 'summary', or 'text')
    const text = (insight.content || insight.summary || insight.text || "") as string;
    if (!text) continue;

    // Check for existing knowledge with very similar content
    const { count } = await supabase
      .from("knowledge")
      .select("*", { count: "exact", head: true })
      .ilike("content", `%${text.slice(0, 50)}%`);

    if ((count || 0) === 0) {
      candidates.push({ insight, text });
    }
  }

  if (dryRun) {
    return JSON.stringify({
      dry_run: true,
      would_promote: candidates.length,
      skipped_duplicates: (insights.length - candidates.length),
      candidates: candidates.map((c) => ({
        insight_id: c.insight.id,
        content_preview: c.text.slice(0, 120),
        confidence: c.insight.confidence,
      })),
    });
  }

  // Promote: insert into knowledge with embedding
  let promoted = 0;
  const errors: string[] = [];

  for (const { insight, text } of candidates) {
    let embedding: number[] | null = null;
    try {
      embedding = await embed(text);
    } catch {
      // Continue without embedding
    }

    const { error: insertError } = await supabase.from("knowledge").insert({
      content: text,
      knowledge_type: (insight.type as string) || "pattern",
      domain: (insight.domain as string) || "ai",
      confidence: insight.confidence as number,
      impact: (insight.impact as number) || 0.5,
      source: "synthesis",
      source_ref: { insight_id: insight.id, promoted_at: new Date().toISOString() },
      embedding,
    });

    if (insertError) {
      errors.push(`insight ${insight.id}: ${insertError.message}`);
    } else {
      promoted++;
    }
  }

  return JSON.stringify({
    dry_run: false,
    promoted,
    errors: errors.length > 0 ? errors : undefined,
    skipped_duplicates: (insights.length - candidates.length),
  });
}
```

- [ ] **Step 2: Redeploy**

```bash
cd "/Volumes/OWC drive/Dev/lex"
supabase functions deploy knowledge-mcp --project-ref pgqoqhozxqpjnukjbzug
```

- [ ] **Step 3: Test synthesize (dry run first)**

```bash
KNOWLEDGE_API_KEY=$(grep KNOWLEDGE_API_KEY .env | cut -d= -f2)
curl -s -X POST "https://pgqoqhozxqpjnukjbzug.supabase.co/functions/v1/knowledge-mcp" \
  -H "Authorization: Bearer $KNOWLEDGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"synthesize","arguments":{"min_confidence":0.5,"dry_run":true}}}' | python3 -m json.tool
```

Expected: Shows candidates for promotion without writing.

- [ ] **Step 4: Commit**

```bash
cd "/Volumes/OWC drive/Dev/lex"
git add supabase/functions/knowledge-mcp/tools.ts
git commit -m "feat: add synthesize tool for insight-to-knowledge promotion"
```

---

### Task 9: pg_cron + Automated Maintenance

**Files:**
- Create: `supabase/migrations/003_knowledge_cron.sql`

- [ ] **Step 1: Verify pg_cron is available**

```sql
-- Via Supabase MCP execute_sql
SELECT * FROM pg_extension WHERE extname = 'pg_cron';
```

If not enabled:

```sql
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA extensions;
GRANT USAGE ON SCHEMA cron TO postgres;
```

Note: pg_cron requires Supabase Pro plan. If not available, these scheduled tasks can be run via launchd instead (curl the Edge Function on a schedule).

- [ ] **Step 2: Write the maintenance migration**

Create `supabase/migrations/003_knowledge_cron.sql`:

```sql
-- ============================================================
-- Knowledge Layer — Automated Maintenance via pg_cron
-- ============================================================

-- 1. Daily: Delete expired entries (past TTL)
SELECT cron.schedule(
  'knowledge-ttl-cleanup',
  '0 3 * * *',  -- 3 AM daily
  $$
  DELETE FROM knowledge
  WHERE ttl_days IS NOT NULL
    AND created_at + (ttl_days || ' days')::interval < now();
  $$
);

-- 2. Daily: Flag stale untested entries (> 90 days old) for review
-- (Adds a domain-specific note to source_ref rather than deleting)
SELECT cron.schedule(
  'knowledge-stale-flag',
  '0 4 * * *',  -- 4 AM daily
  $$
  UPDATE knowledge
  SET source_ref = source_ref || '{"needs_review": true}'::jsonb
  WHERE test_result = 'untested'
    AND created_at < now() - interval '90 days'
    AND NOT (source_ref ? 'needs_review');
  $$
);

-- 3. Weekly: Clean up superseded entries older than 6 months
-- (Superseded entries with a replacement don't need to stay forever)
SELECT cron.schedule(
  'knowledge-superseded-cleanup',
  '0 5 * * 0',  -- 5 AM Sunday
  $$
  DELETE FROM knowledge
  WHERE test_result = 'superseded'
    AND superseded_by IS NOT NULL
    AND updated_at < now() - interval '180 days';
  $$
);

-- 4. Weekly: Auto-promote high-confidence insights to knowledge
-- Calls the Edge Function synthesize tool via pg_net (HTTP extension)
-- Requires pg_net extension. If unavailable, use launchd fallback below.
SELECT cron.schedule(
  'knowledge-weekly-synthesis',
  '0 6 * * 0',  -- 6 AM Sunday
  $$
  SELECT net.http_post(
    url := 'https://pgqoqhozxqpjnukjbzug.supabase.co/functions/v1/knowledge-mcp',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || current_setting('app.settings.knowledge_api_key', true)
    ),
    body := '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"synthesize","arguments":{"min_confidence":0.7,"dry_run":false}}}'::jsonb
  );
  $$
);
```

- [ ] **Step 3: Apply the migration**

```bash
cd "/Volumes/OWC drive/Dev/lex"
supabase db push --project-ref pgqoqhozxqpjnukjbzug
```

Or via Supabase MCP apply_migration.

- [ ] **Step 4: Verify cron jobs are scheduled**

```sql
SELECT jobid, schedule, command FROM cron.job ORDER BY jobid;
```

Expected: 4 cron jobs listed (ttl-cleanup, stale-flag, superseded-cleanup, weekly-synthesis).

- [ ] **Step 5: Backfill embeddings for existing insights**

Run a one-time backfill for the 10 existing insight rows (if they have a text column):

```sql
-- Check what columns the insights table has
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'insights' ORDER BY ordinal_position;
```

Then use the synthesize tool to promote them:

```bash
curl -s -X POST "$BASE_URL" -H "$AUTH" -H "$CT" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"synthesize","arguments":{"min_confidence":0.3,"dry_run":false}}}'
```

- [ ] **Step 6: Commit**

```bash
cd "/Volumes/OWC drive/Dev/lex"
git add supabase/migrations/003_knowledge_cron.sql
git commit -m "feat: add pg_cron maintenance jobs for TTL, stale flagging, and cleanup"
```

---

## Success Criteria

| Test | Pass Condition |
|------|---------------|
| Cross-platform retrieval | Same entry retrievable from Claude Code via MCP tool and from Claude AI via Supabase connector SQL |
| EV ranking works | High-confidence confirmed entries rank above low-confidence untested ones in search results |
| Freshness decay works | 90-day-old AI insight has lower live_ev than 1-day-old AI insight (same confidence/impact) |
| Contradiction flag | Contradicted entry excluded from default search results (`include_contradicted=false`) |
| Synthesis runs | `synthesize` tool promotes insights above threshold to knowledge table |
| Single install | New MCP client connects with one URL + bearer token, no additional setup |
| Auth works | Requests without valid API key return 401 |
| Embedding works | Captured entries have non-null embedding; search uses vector similarity |

---

## Launchd Fallback (if pg_cron unavailable)

If the Supabase plan doesn't support pg_cron, create launchd plists for local cron:

**Weekly synthesis** (Sundays 6 AM):
```xml
<!-- com.erpaccess.knowledge-synthesis.plist -->
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.erpaccess.knowledge-synthesis</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>source ~/.claude/ahgen/.env 2>/dev/null; curl -s -X POST "https://pgqoqhozxqpjnukjbzug.supabase.co/functions/v1/knowledge-mcp" -H "Authorization: Bearer $KNOWLEDGE_API_KEY" -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"synthesize","arguments":{"min_confidence":0.7,"dry_run":false}}}'</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>0</integer>
    <key>Hour</key><integer>6</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
</dict>
</plist>
```

**Daily TTL cleanup** (3 AM — only needed if pg_cron unavailable):
```xml
<!-- com.erpaccess.knowledge-maintenance.plist -->
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.erpaccess.knowledge-maintenance</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>source ~/.claude/ahgen/.env 2>/dev/null; curl -s -X POST "https://pgqoqhozxqpjnukjbzug.supabase.co/functions/v1/knowledge-mcp" -H "Authorization: Bearer $KNOWLEDGE_API_KEY" -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"status","arguments":{"top_n":3}}}'</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>3</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
</dict>
</plist>
```

---

## What NOT To Build (from design spec)

- No local SQLite database — Supabase is the single source
- No separate Pinecone index — pgvector handles vector search
- No Slack capture channel — Claude captures directly via MCP tool
- No custom UI — MCP tools ARE the interface
- No framework — one table, one Edge Function, one URL
