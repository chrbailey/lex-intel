# Lex Intel Multi-Agent Orchestration Architecture

## Date: February 15, 2026

## TL;DR -- The Answer

**Yes, use Claude's built-in Agent Teams + Agent SDK. Do not build custom orchestration.**

Agent Teams was released February 5, 2026 -- ten days ago. It does exactly what you need: a lead agent spawns specialized teammates, each with its own context window, and they communicate via messaging. This is Anthropic-native, runs on your Claude Max account, and handles the orchestration plumbing you'd otherwise spend months building.

Your time is better spent writing precise agent definitions (what each agent does, what tools it has, what data it accesses) than building infrastructure. The infrastructure already exists.

---

## What Already Exists in Lex Intel

Before designing the multi-agent layer, here's what you already have working:

| Component | Status | Location |
|-----------|--------|----------|
| 11-source Chinese tech scraper pipeline | Working | `lib/scrape.py` |
| Two-stage LLM analysis (translate + briefing) | Working | `lib/analyze.py` |
| Supabase database (articles, briefings, publish queue) | Working | `lib/db.py` |
| Pinecone vector search + semantic dedup | Working | `lib/vectors.py` |
| 5-platform publishing (LinkedIn, Dev.to, Hashnode, Blogger, Medium) | Working | `lib/publish.py` |
| MCP server with 11 tools (7 read, 4 write) | Working | `lex_server.py` |
| CLI with 8 commands | Working | `lex.py` |
| Gmail briefing delivery | Working | `lib/email.py` |
| Daily scheduling (macOS launchd) | Working | `setup/` |
| Test suite (1,900 LOC) | Working | `tests/` |

You have a solid, production-grade intelligence pipeline. The multi-agent layer sits **on top of** this -- it doesn't replace it.

---

## The Decision: Built-In vs. Custom

### Option A: Claude Agent Teams + Agent SDK (Recommended)

**What it is:** Anthropic's native multi-agent system. A lead agent creates a team, spawns teammates (each with its own context window, role, and tools), and teammates communicate via messaging. Released Feb 5, 2026.

**Pros:**
- Zero orchestration code to write -- Anthropic handles scheduling, context, messaging
- Runs on Claude Max Ultimate ($200/mo) with background execution
- Each agent gets a full context window (1M tokens on Opus 4.6)
- Native MCP integration -- your existing `lex_server.py` tools are immediately available
- Agent definitions are just markdown files + `AgentDefinition` configs
- Proven at scale: 16 agents built a 100,000-line C compiler autonomously

**Cons:**
- Tied to Anthropic's ecosystem (which you've chosen deliberately)
- Agent Teams is 10 days old -- API surface may evolve
- Requires Claude Max for sustained background execution

### Option B: CrewAI / LangGraph / Custom Python

**What it is:** Third-party frameworks or custom code for agent orchestration.

**Pros:**
- LLM-agnostic (can swap models)
- More mature (CrewAI: 60M+ agent executions/month)
- Finer-grained control over scheduling and state

**Cons:**
- Significant development effort (weeks to months)
- Another dependency to maintain
- You lose Anthropic-native optimizations
- Still calling Claude API underneath -- extra abstraction layer for no gain
- CrewAI/LangGraph are designed for teams with dedicated engineers

### Verdict

You described wanting to stay native to Anthropic and ride their roadmap. Agent Teams + Agent SDK is exactly that. The framework handles orchestration; you define agent roles, tools, and data flows. This is the correct call for your situation.

---

## The Six-Agent Architecture

### Overview

```
                    +------------------+
                    |  Agent 6: CHIEF  |
                    |  (Orchestrator)  |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v--+   +------v-----+   +----v-------+
     | Agent 1:  |   | Agent 3:   |   | Agent 5:   |
     | SCOUT     |   | STRATEGIST |   | EXECUTOR   |
     | (Research)|   | (Opps +    |   | (Action    |
     |           |   |  Projects) |   |  Plans)    |
     +--------+--+   +------+-----+   +------------+
              |              |
     +--------v--+   +------v-----+
     | Agent 2:  |   | Agent 4:   |
     | ANALYST   |   | SYNTHESIZER|
     | (Deep     |   | + Guest    |
     |  Analysis)|   |  Agent     |
     +----------+   +------------+
```

### Agent Definitions

#### Agent 1: SCOUT (Research Agent)

**Role:** Continuous research across all intelligence sources.

**What it does:**
- Runs the existing scrape pipeline (`lex_run_scrape`)
- Expands beyond current 11 Chinese sources to global AI/tech sources
- Monitors competitor activity, patent filings, market reports
- Searches for emerging opportunities in AI tooling, automation, government contracts
- Tracks SDVOSB (Service-Disabled Veteran-Owned Small Business) set-aside opportunities on SAM.gov, GSA, and DoD platforms
- Scans for grants, SBIR/STTR opportunities relevant to AI/automation

**Tools (MCP):**
- `lex_run_scrape` (existing)
- `lex_search_articles` (existing)
- Web search / Fetch tools
- SAM.gov API (new MCP server)
- RSS feed aggregator (new MCP server)

**Output:** Raw research data stored in Supabase `research_items` table with embeddings in pgvector.

**Schedule:** Daily (automated), with ad-hoc deep dives triggered by other agents.

---

#### Agent 2: ANALYST (Deep Analysis Agent)

**Role:** Analyze all research from Agent 1 and existing Lex Intel data.

**What it does:**
- Runs the existing analysis pipeline (`lex_run_analyze`) for Chinese AI intel
- Performs deep analysis on new research items from Scout
- Identifies patterns, trends, and anomalies across all data
- Generates intelligence briefings with confidence scores
- Flags items requiring human attention (high-impact, time-sensitive)
- Cross-references current intel with historical context (Supabase + pgvector)

**Tools (MCP):**
- `lex_run_analyze` (existing)
- `lex_get_signals` (existing)
- `lex_get_trending` (existing)
- `lex_search_articles` (existing)
- Supabase pgvector similarity search (new)

**Output:** Analyzed research with categorization, relevance scores, trend analysis, and briefings stored in Supabase `analysis_reports` table.

**Schedule:** Runs after Scout completes each cycle. Also triggered on-demand.

---

#### Agent 3: STRATEGIST (Opportunity + Projects Agent)

**Role:** Scan across the entire codebase and business for opportunities.

**What it does:**
- Reviews all active projects across your codebases (not just lex-intel)
- Identifies monetization opportunities from analyzed intelligence
- Maps SDVOSB set-aside contracts to your capabilities
- Evaluates technology gaps you could fill with existing tools
- Identifies partnership and subcontracting opportunities
- Tracks which of your published content drives engagement (using existing publish analytics)
- Proposes new products/services based on market signals

**Tools (MCP):**
- GitHub MCP (access to all repos)
- Supabase MCP (all project databases)
- `lex_get_briefing`, `lex_get_signals`, `lex_get_trending` (existing)
- Financial/market data APIs (new MCP servers as needed)

**Output:** Opportunity assessments stored in Supabase `opportunities` table with priority scores and required actions.

**Schedule:** Weekly deep analysis. Daily quick scan of new intel from Analyst.

---

#### Agent 4: SYNTHESIZER + Weekly Guest Agent

**Role:** Combined analysis with Strategist + fresh perspective from rotating guest agent.

**What it does:**
- Takes Analyst's processed intelligence and Strategist's opportunity assessments
- Synthesizes cross-domain insights (what does Chinese AI regulation mean for your SDVOSB opportunities?)
- The "Guest Agent" is a weekly rotation of specialized perspectives:
  - Week 1: Market Analyst (revenue modeling, pricing, TAM)
  - Week 2: Technical Architect (feasibility, build vs. buy, stack decisions)
  - Week 3: Growth Hacker (distribution, content strategy, lead generation)
  - Week 4: Risk Assessor (compliance, security, competitive threats)
- Guest agent challenges assumptions from Agents 2 and 3
- Generates novel ideas by combining domains the other agents don't cross-reference

**Tools (MCP):**
- All read tools from Lex Intel MCP
- Supabase MCP (full access to all analysis and opportunity data)
- Web search for guest-agent-specific research

**Output:** Synthesis reports with novel ideas, challenged assumptions, and scored recommendations stored in Supabase `synthesis_reports` table.

**Schedule:** Weekly (after Strategist completes weekly deep analysis).

**Guest Agent Implementation:** The guest agent is simply a different system prompt loaded each week. The `AgentDefinition` in the SDK supports per-agent `prompt` fields. A simple rotation based on `week_number % 4` selects the appropriate prompt.

---

#### Agent 5: EXECUTOR (Actionable Plans Agent)

**Role:** Convert all upstream analysis into concrete, actionable plans.

**What it does:**
- Takes synthesis reports, opportunity assessments, and intelligence briefings
- Creates specific, time-bound action items with clear deliverables
- Prioritizes by impact, effort, and deadline
- Handles the "last mile" of turning intelligence into work:
  - Draft proposals for government contracts
  - Create content calendars for publishing
  - Generate outreach templates for partnerships
  - Prepare invoices and follow-up sequences
  - Draft responses to customer complaints (professional, not curt)
  - Schedule social media posts via the existing publish pipeline
- Manages the publish queue for content that agents generate

**Tools (MCP):**
- `lex_run_publish` (existing)
- Supabase MCP (write to action_items table)
- Email MCP (drafting, not sending -- human approval required for outbound)
- Calendar/scheduling APIs (new MCP servers)
- Document generation (proposals, invoices)

**Output:** Action items in Supabase `action_items` table with status tracking, deadlines, and assignments.

**Schedule:** Runs after Synthesizer completes. Also runs daily to manage ongoing action items.

---

#### Agent 6: CHIEF (Orchestrator / Project Manager)

**Role:** The lead agent that coordinates all other agents.

**What it does:**
- This is the Agent Teams "lead" in Claude's native system
- Spawns and monitors all five specialist agents
- Decides when to trigger agent runs based on data availability
- Reviews agent outputs for quality (acts as a quality gate)
- Escalates to human (you) only when necessary:
  - Financial commitments above a threshold
  - Customer-facing communications
  - Contract submissions
  - Anything flagged as "needs human review"
- Maintains the master dashboard / status view
- Sends you a daily digest: what happened, what's pending, what needs your attention
- Manages the weekly guest agent rotation

**Tools (MCP):**
- All Lex Intel MCP tools
- Agent Teams messaging (native)
- Supabase MCP (full access)
- Email MCP (for daily digest to you)
- Notification system (for escalations)

**Output:** Daily digest email, escalation alerts, agent health monitoring.

**Schedule:** Always running. Checks agent status every hour. Sends digest at end of day.

**Key Design Decision:** Chief does NOT replace Claude Code's built-in Agent Teams orchestration. It IS the lead agent in the Agent Teams system. The Agent SDK handles the actual spawning, messaging, and lifecycle. Chief's prompt defines the coordination logic.

---

## Data Architecture: Consolidate on Supabase

### Why Move from Pinecone to Supabase pgvector

Your current Lex Intel data is split: structured data in Supabase, vectors in Pinecone. For the multi-agent system, consolidate on Supabase.

**Reasons:**
1. Your vector count is tiny (<100K). pgvector handles this trivially.
2. Agents need hybrid queries (SQL filters + semantic search) constantly. Two databases means two round trips.
3. pgvectorscale (DiskANN extension) now makes pgvector viable up to ~50M vectors. You won't hit that in 2026.
4. One connection string, one auth system, one bill. Simpler ops.
5. ACID transactions across structured + vector data. Critical for agent coordination.
6. In benchmarks, pgvector actually outperforms Pinecone in accuracy and QPS on equivalent resources.
7. You're already paying for Supabase. Pinecone is an extra bill.

### New Tables for Multi-Agent System

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Research items from Scout agent
CREATE TABLE research_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source      TEXT NOT NULL,          -- 'sam_gov', 'rss', 'web_search', etc.
    source_url  TEXT,
    title       TEXT NOT NULL,
    body        TEXT,
    category    TEXT,                   -- 'opportunity', 'technology', 'market', etc.
    relevance   SMALLINT CHECK (relevance BETWEEN 1 AND 5),
    agent_id    TEXT DEFAULT 'scout',
    embedding   VECTOR(1536),          -- pgvector embedding
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Analysis reports from Analyst agent
CREATE TABLE analysis_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type     TEXT NOT NULL,      -- 'trend', 'anomaly', 'briefing', 'pattern'
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    confidence      REAL CHECK (confidence BETWEEN 0 AND 1),
    source_items    UUID[],            -- references to research_items and articles
    agent_id        TEXT DEFAULT 'analyst',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Opportunities from Strategist agent
CREATE TABLE opportunities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    opp_type        TEXT NOT NULL,      -- 'contract', 'product', 'partnership', 'content'
    priority        SMALLINT CHECK (priority BETWEEN 1 AND 5),
    estimated_value TEXT,               -- '$10K-50K', 'recurring $2K/mo', etc.
    deadline        DATE,
    source_reports  UUID[],            -- references to analysis_reports
    status          TEXT DEFAULT 'identified',  -- identified, evaluating, pursuing, won, lost, declined
    agent_id        TEXT DEFAULT 'strategist',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Synthesis reports from Synthesizer + Guest agents
CREATE TABLE synthesis_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    guest_persona   TEXT,              -- 'market_analyst', 'tech_architect', etc.
    novel_ideas     JSONB DEFAULT '[]',
    challenged      JSONB DEFAULT '[]', -- assumptions that were challenged
    recommendations JSONB DEFAULT '[]',
    source_data     UUID[],            -- references to analysis_reports + opportunities
    agent_id        TEXT DEFAULT 'synthesizer',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Action items from Executor agent
CREATE TABLE action_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    action_type     TEXT NOT NULL,      -- 'proposal', 'content', 'outreach', 'invoice', 'follow_up'
    priority        SMALLINT CHECK (priority BETWEEN 1 AND 5),
    status          TEXT DEFAULT 'pending', -- pending, in_progress, blocked, completed, cancelled
    deadline        DATE,
    deliverable     TEXT,              -- what the output should be
    source_reports  UUID[],            -- references to synthesis_reports or opportunities
    output          JSONB DEFAULT '{}', -- the actual deliverable (draft, template, etc.)
    requires_human  BOOLEAN DEFAULT FALSE,
    agent_id        TEXT DEFAULT 'executor',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

-- Agent run log (for Chief to monitor)
CREATE TABLE agent_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT NOT NULL,      -- 'scout', 'analyst', 'strategist', etc.
    status          TEXT NOT NULL,      -- 'started', 'completed', 'failed', 'timeout'
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    duration_s      INTEGER,
    items_processed INTEGER DEFAULT 0,
    items_created   INTEGER DEFAULT 0,
    error           TEXT,
    metadata        JSONB DEFAULT '{}'
);

-- Indexes
CREATE INDEX idx_research_items_embedding ON research_items
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_research_items_category ON research_items(category);
CREATE INDEX idx_research_items_created ON research_items(created_at DESC);
CREATE INDEX idx_analysis_reports_type ON analysis_reports(report_type);
CREATE INDEX idx_opportunities_status ON opportunities(status);
CREATE INDEX idx_opportunities_priority ON opportunities(priority DESC);
CREATE INDEX idx_action_items_status ON action_items(status);
CREATE INDEX idx_action_items_deadline ON action_items(deadline);
CREATE INDEX idx_action_items_requires_human ON action_items(requires_human) WHERE requires_human = TRUE;
CREATE INDEX idx_agent_runs_agent ON agent_runs(agent_id, started_at DESC);
```

### Data Flow

```
Scout (research_items)
    |
    v
Analyst (analysis_reports) -----> existing articles table (enriched)
    |                              |
    v                              v
Strategist (opportunities) <--- existing briefings
    |
    v
Synthesizer (synthesis_reports)  <--- Guest Agent (weekly rotation)
    |
    v
Executor (action_items) ---------> existing publish_queue
    |
    v
Chief (agent_runs) -- monitors all tables, sends daily digest
```

---

## Implementation Plan

### Phase 1: Foundation (Do This First)

1. **Migrate from Pinecone to Supabase pgvector**
   - Enable `vector` extension in Supabase
   - Add `embedding VECTOR(1536)` column to `articles` table
   - Rewrite `lib/vectors.py` to use Supabase pgvector instead of Pinecone
   - Backfill existing article embeddings (use Anthropic's embedding model or Voyage AI)
   - Update tests
   - Remove Pinecone dependency from `requirements.txt`

2. **Create the new tables** (schema above)
   - Add migration `002_multi_agent_schema.sql`

3. **Set up Claude Agent SDK**
   - Install: `pip install claude-agent-sdk` (or `npm install @anthropic-ai/claude-code-sdk`)
   - Create agent definition files in `.claude/agents/`

### Phase 2: Agent Definitions (Your Main Work)

This is where you spend your time. Each agent needs:

```
.claude/agents/
    scout.md          -- Agent 1: Research
    analyst.md        -- Agent 2: Deep Analysis
    strategist.md     -- Agent 3: Opportunities
    synthesizer.md    -- Agent 4: Synthesis + Guest
    executor.md       -- Agent 5: Action Plans
    chief.md          -- Agent 6: Orchestrator
    guests/
        market-analyst.md
        tech-architect.md
        growth-hacker.md
        risk-assessor.md
```

Each `.md` file defines:
- Role and responsibilities
- Available tools (MCP servers)
- Input data sources (which Supabase tables to read)
- Output format (which tables to write to)
- Quality criteria (what "good output" looks like)
- Escalation rules (when to flag for human review)

**This is exactly where you should spend your time.** The more precise these definitions are, the better the agents perform. You don't need to write orchestration code -- the Agent SDK handles that. You write the "job descriptions."

### Phase 3: MCP Server Expansion

Add new MCP tools to `lex_server.py` or create additional MCP servers:

```python
# New tools for multi-agent system
@mcp.tool()
def lex_store_research(title, body, source, category, relevance): ...
@mcp.tool()
def lex_store_analysis(report_type, title, body, confidence, source_items): ...
@mcp.tool()
def lex_store_opportunity(title, description, opp_type, priority, deadline): ...
@mcp.tool()
def lex_store_action_item(title, description, action_type, priority, deadline): ...
@mcp.tool()
def lex_get_pending_actions(status, requires_human): ...
@mcp.tool()
def lex_log_agent_run(agent_id, status, items_processed, items_created): ...
@mcp.tool()
def lex_vector_search(query, table, limit, min_similarity): ...
```

### Phase 4: Orchestration Script

A simple Python script that uses the Agent SDK to run the daily cycle:

```python
# orchestrate.py (conceptual -- actual SDK API may differ slightly)
from claude_agent_sdk import AgentTeam, AgentDefinition

team = AgentTeam(
    lead=AgentDefinition.from_file(".claude/agents/chief.md"),
    teammates=[
        AgentDefinition.from_file(".claude/agents/scout.md"),
        AgentDefinition.from_file(".claude/agents/analyst.md"),
        AgentDefinition.from_file(".claude/agents/strategist.md"),
        AgentDefinition.from_file(".claude/agents/synthesizer.md"),
        AgentDefinition.from_file(".claude/agents/executor.md"),
    ],
    mcp_servers=["lex-intel"],
    model="opus",
    permission_mode="bypassPermissions",  # agents run autonomously
)

# Chief decides the execution order and triggers agents
await team.run("Execute daily intelligence cycle. Check agent_runs for last completion times.")
```

### Phase 5: Scheduling

Replace macOS launchd with a persistent runner:

```bash
# cron or systemd or cloud scheduler
# Daily at 7 AM China time (11 PM Pacific):
python orchestrate.py --mode daily

# Weekly (Sunday evening):
python orchestrate.py --mode weekly --guest-rotation
```

---

## Cost Estimate

| Component | Monthly Cost |
|-----------|-------------|
| Claude Max Ultimate | $200 |
| Supabase Pro | $25 |
| Pinecone | $0 (removed) |
| Domain/hosting | ~$10 |
| **Total** | **~$235/mo** |

Compare to building this with API keys directly: heavy agentic usage could easily exceed $3,650/month. Max Ultimate at $200/month is roughly 18x cheaper for equivalent usage.

---

## What You Should NOT Build

1. **Custom orchestration framework** -- Agent Teams does this
2. **Agent-to-agent messaging system** -- TeammateTool handles this
3. **Job scheduler** -- A simple cron + the SDK is sufficient
4. **Dashboard UI** -- Supabase has a built-in table viewer; use it until you need more
5. **Custom embedding pipeline** -- Supabase pgvector with Voyage AI or Anthropic embeddings
6. **Retry/error handling for agents** -- Chief agent handles this via its prompt

---

## What You SHOULD Build (or Define)

1. **Agent definition files** (the `.md` files above) -- this is your primary work
2. **New Supabase tables** (migration file)
3. **New MCP tools** (extend `lex_server.py`)
4. **Pinecone-to-pgvector migration** (rewrite `lib/vectors.py`)
5. **The orchestration script** (~50 lines of Python)
6. **Guest agent prompts** (4 rotating perspectives)

---

## On Your Personal Situation

The architecture above is designed for your specific needs:

- **Autonomous operation**: Agents run without you being at the computer. Chief sends a daily digest. You review when you can.
- **Minimal human interaction**: Customer complaints get professional, measured draft responses. You approve or edit before sending. The system is the buffer between you and human contact.
- **Single focus**: Each day, your digest tells you the ONE thing that needs attention. Everything else is handled or queued.
- **Continuity**: All state is in Supabase. If you lose your train of thought, the database is the source of truth. Pick up where you left off by asking any agent "what's the current status?"
- **Growth without complexity**: Adding a new agent is adding a new `.md` file. Adding a new data source is adding a new MCP tool. The architecture scales without rewiring.

---

## Next Steps (In Order)

1. Enable pgvector in Supabase and create migration `002_multi_agent_schema.sql`
2. Rewrite `lib/vectors.py` to use Supabase pgvector
3. Write the six agent definition files in `.claude/agents/`
4. Write the four guest agent prompts in `.claude/agents/guests/`
5. Add new MCP tools to `lex_server.py`
6. Create `orchestrate.py` using Claude Agent SDK
7. Set up scheduling (cron or systemd)
8. Run the first cycle and iterate on agent prompts based on output quality
