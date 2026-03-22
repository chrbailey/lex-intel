import { type SupabaseClient } from "jsr:@supabase/supabase-js@2";
import { calculateLiveEV } from "../_shared/ev.ts";
import { embed } from "../_shared/embed.ts";

// ─── Tool Definitions ────────────────────────────────────────

export const TOOL_DEFINITIONS = [
  {
    name: "capture",
    description:
      "Store new knowledge with type, domain, confidence, and impact. Auto-embeds for semantic search.",
    inputSchema: {
      type: "object",
      properties: {
        content: {
          type: "string",
          description: "The knowledge entry (one idea per entry)",
        },
        knowledge_type: {
          type: "string",
          enum: [
            "fact",
            "decision",
            "pattern",
            "lesson",
            "preference",
            "context",
          ],
          default: "fact",
        },
        domain: {
          type: "string",
          description:
            "Domain: ai, erp, fishing, personal, stanford, business, general",
          default: "general",
        },
        confidence: {
          type: "number",
          minimum: 0,
          maximum: 1,
          default: 0.5,
          description: "How certain is this?",
        },
        impact: {
          type: "number",
          minimum: 0,
          maximum: 1,
          default: 0.5,
          description: "How much does acting on this change outcomes?",
        },
        source: {
          type: "string",
          default: "manual",
          description: "conversation, observation, synthesis, or manual",
        },
        source_ref: {
          type: "object",
          default: {},
          description: "Chat URI, insight ID, signal ID, or external URL",
        },
        ttl_days: {
          type: "number",
          description: "Auto-expire after N days (omit for permanent)",
        },
      },
      required: ["content"],
    },
  },
  {
    name: "search",
    description:
      "Semantic search via pgvector embedding similarity, ranked by expected value (confidence × impact × freshness).",
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Natural language search query",
        },
        domain: { type: "string", description: "Filter by domain" },
        knowledge_type: { type: "string", description: "Filter by type" },
        min_confidence: {
          type: "number",
          default: 0,
          description: "Minimum confidence threshold",
        },
        limit: { type: "number", default: 10, maximum: 50 },
        include_contradicted: { type: "boolean", default: false },
      },
      required: ["query"],
    },
  },
  {
    name: "validate",
    description:
      "Mark knowledge as confirmed, contradicted, or superseded. Updates confidence accordingly.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Knowledge entry UUID" },
        test_result: {
          type: "string",
          enum: ["confirmed", "contradicted", "superseded"],
        },
        superseded_by: {
          type: "string",
          description: "UUID of replacement entry (when superseded)",
        },
        notes: {
          type: "string",
          description: "Why this validation was made",
        },
      },
      required: ["id", "test_result"],
    },
  },
  {
    name: "synthesize",
    description:
      "Promote high-confidence insights to knowledge entries. Preview with dry_run=true first.",
    inputSchema: {
      type: "object",
      properties: {
        min_confidence: {
          type: "number",
          default: 0.7,
          description: "Minimum insight confidence for promotion",
        },
        dry_run: {
          type: "boolean",
          default: true,
          description: "Preview what would be promoted without writing",
        },
      },
    },
  },
  {
    name: "status",
    description:
      "System health: counts by type/domain, top EV entries, untested entries, entries expiring soon.",
    inputSchema: {
      type: "object",
      properties: {
        top_n: {
          type: "number",
          default: 5,
          description: "How many top EV entries to return",
        },
      },
    },
  },
  {
    name: "query_signals",
    description:
      "Direct access to raw_signals table for ad-hoc analysis of collected signals.",
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Text search in signal content",
        },
        source: { type: "string", description: "Filter by signal source" },
        limit: { type: "number", default: 20 },
        since: {
          type: "string",
          description: "ISO date — only signals after this date",
        },
      },
    },
  },
];

// ─── Tool Dispatch ───────────────────────────────────────────

type ToolResult = { content: Array<{ type: string; text: string }> };

export async function handleToolCall(
  supabase: SupabaseClient,
  name: string,
  args: Record<string, unknown>,
): Promise<ToolResult> {
  const handlers: Record<
    string,
    (sb: SupabaseClient, a: Record<string, unknown>) => Promise<string>
  > = {
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
  args: Record<string, unknown>,
): Promise<string> {
  const content = args.content as string;

  // Generate embedding (non-blocking: store without embedding if API fails)
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
  args: Record<string, unknown>,
): Promise<string> {
  const query = args.query as string;
  const limit = Math.min((args.limit as number) || 10, 50);
  const domain = (args.domain as string) || null;
  const knowledgeType = (args.knowledge_type as string) || null;
  const minConfidence = (args.min_confidence as number) || 0;
  const includeContradicted =
    (args.include_contradicted as boolean) || false;

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
        r.ttl_days as number | null,
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
      similarity: r.similarity
        ? Number((r.similarity as number).toFixed(4))
        : null,
      source: r.source,
      created_at: r.created_at,
    })),
  });
}

// ─── validate ────────────────────────────────────────────────

async function handleValidate(
  supabase: SupabaseClient,
  args: Record<string, unknown>,
): Promise<string> {
  const id = args.id as string;
  const newResult = args.test_result as string;
  const supersededBy = (args.superseded_by as string) || null;
  const notes = (args.notes as string) || null;

  // Fetch current entry
  const { data: current, error: fetchError } = await supabase
    .from("knowledge")
    .select("confidence, test_result, source_ref")
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
      newConfidence = 0;
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
    update.source_ref = {
      ...(current.source_ref || {}),
      validation_notes: notes,
    };
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

// ─── synthesize ──────────────────────────────────────────────

async function handleSynthesize(
  supabase: SupabaseClient,
  args: Record<string, unknown>,
): Promise<string> {
  const minConfidence = (args.min_confidence as number) || 0.7;
  const dryRun = (args.dry_run as boolean) ?? true;

  // Fetch insights above confidence threshold
  const { data: insights, error: fetchError } = await supabase
    .from("insights")
    .select("*")
    .gte("confidence", minConfidence)
    .order("confidence", { ascending: false });

  if (fetchError) {
    return JSON.stringify({
      error: `Failed to fetch insights: ${fetchError.message}`,
      hint: "The insights table may not exist yet. It will be created when signal synthesis is set up.",
    });
  }

  if (!insights || insights.length === 0) {
    return JSON.stringify({
      promoted: 0,
      message: `No insights found with confidence >= ${minConfidence}`,
    });
  }

  // Check which insights are already in knowledge (dedup)
  const candidates = [];
  for (const insight of insights) {
    const text = (insight.content || insight.summary || insight.text || "") as string;
    if (!text) continue;

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
      skipped_duplicates: insights.length - candidates.length,
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
    skipped_duplicates: insights.length - candidates.length,
  });
}

// ─── status ──────────────────────────────────────────────────

async function handleStatus(
  supabase: SupabaseClient,
  args: Record<string, unknown>,
): Promise<string> {
  const topN = (args.top_n as number) || 5;

  // Total count
  const { count: total } = await supabase
    .from("knowledge")
    .select("*", { count: "exact", head: true });

  // All entries for aggregation
  const { data: allEntries } = await supabase
    .from("knowledge")
    .select("knowledge_type, domain");

  const byType: Record<string, number> = {};
  const byDomain: Record<string, number> = {};
  for (const r of allEntries || []) {
    byType[r.knowledge_type] = (byType[r.knowledge_type] || 0) + 1;
    byDomain[r.domain] = (byDomain[r.domain] || 0) + 1;
  }

  // Top N by EV (fetch extra to re-rank after decay)
  const { data: topEntries } = await supabase
    .from("knowledge")
    .select(
      "id, content, confidence, impact, domain, expected_value, test_result, created_at, ttl_days",
    )
    .neq("test_result", "contradicted")
    .order("expected_value", { ascending: false })
    .limit(topN * 2);

  const ranked = (topEntries || [])
    .map((r) => ({
      ...r,
      live_ev: calculateLiveEV(
        r.confidence as number,
        r.impact as number,
        r.created_at as string,
        r.domain as string,
        r.ttl_days as number | null,
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

  const expiring = (expiringSoon || []).filter((r) => {
    const ageMs = Date.now() - new Date(r.created_at as string).getTime();
    const ageDays = ageMs / (24 * 60 * 60 * 1000);
    const daysRemaining = (r.ttl_days as number) - ageDays;
    return daysRemaining > 0 && daysRemaining <= 30;
  });

  return JSON.stringify({
    total: total || 0,
    by_type: byType,
    by_domain: byDomain,
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

// ─── query_signals ───────────────────────────────────────────

async function handleQuerySignals(
  supabase: SupabaseClient,
  args: Record<string, unknown>,
): Promise<string> {
  const query = (args.query as string) || null;
  const source = (args.source as string) || null;
  const limit = Math.min((args.limit as number) || 20, 100);
  const since = (args.since as string) || null;

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
    return JSON.stringify({
      error: `query_signals failed: ${error.message}`,
      hint:
        "The raw_signals table may not exist yet. It will be created when signal ingestion is set up.",
    });
  }

  return JSON.stringify({
    count: (data || []).length,
    signals: data || [],
  });
}
