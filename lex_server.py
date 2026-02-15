#!/usr/bin/env python3
"""
Lex Intel MCP Server — Chinese AI intelligence for AI agents.

Serves curated, daily Chinese tech/AI intelligence through semantic search,
briefings, and trend signals. Data sourced from 11 Chinese-language outlets
(36Kr, Huxiu, CSDN, Caixin, etc.) plus Gmail newsletters.

Run: python lex_server.py           (stdio transport)
     fastmcp run lex_server.py:mcp  (custom transport)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

# Load .env from project root
_ENV_PATH = Path(__file__).parent / ".env"
if _ENV_PATH.exists():
    for _line in _ENV_PATH.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

mcp = FastMCP(
    "Lex Intel",
    instructions=(
        "Lex Intel provides curated Chinese AI/tech intelligence. "
        "Read tools: lex_search_articles (topic queries), lex_get_briefing "
        "(daily briefing), lex_get_signals (emerging trends), lex_list_sources "
        "(source health), lex_get_trending (category momentum), lex_get_article "
        "(full article detail), lex_get_status (pipeline health), "
        "lex_vector_search (semantic pgvector search), lex_get_pending_actions "
        "(action items by status), lex_get_opportunities (opportunities by status/type), "
        "lex_get_daily_digest (daily agent activity summary). "
        "Write tools: lex_run_scrape (fetch new articles), lex_run_analyze "
        "(translate + categorize + briefing), lex_run_publish (drain publish "
        "queue), lex_run_cycle (full pipeline: scrape + analyze + publish). "
        "Multi-agent write tools: lex_store_research (Scout stores research items), "
        "lex_store_analysis (Analyst stores reports), lex_store_opportunity "
        "(Strategist stores opportunities), lex_store_action_item (Executor stores "
        "action items), lex_log_agent_run (log agent execution metadata). "
        "Write tools modify database state and call external APIs. "
        "All data is sourced from 11 Chinese-language outlets and translated to English."
    ),
)


# ── Tool 1: Search Articles ────────────────────────────────

@mcp.tool
def lex_search_articles(
    query: str,
    limit: int = 10,
    category: Optional[str] = None,
    min_relevance: int = 1,
) -> dict:
    """Search the Chinese AI article corpus by semantic similarity.

    Use this when looking for articles about a specific topic, company,
    technology, or event in the Chinese AI/tech ecosystem.

    Args:
        query: Natural language search query (e.g., "robotics funding",
               "DeepSeek model release", "China AI regulation")
        limit: Max results to return (1-50, default 10)
        category: Filter by category. One of: funding, m_and_a, investment,
                  product, regulation, breakthrough, research, open_source,
                  partnership, adoption, personnel, market, other.
                  Omit to search all categories.
        min_relevance: Minimum relevance score 1-5 (default 1 = all)

    Returns dict with 'articles' list and 'total' count. Each article has:
    source, english_title, category, relevance, published_at, score.
    """
    from lib.vectors import search

    limit = max(1, min(limit, 50))
    results = search(query, top_k=limit * 2)  # over-fetch for filtering

    articles = []
    for r in results:
        if min_relevance > 1 and r.get("relevance", 0) < min_relevance:
            continue
        if category and r.get("category") != category:
            continue
        articles.append({
            "source": r["source"],
            "english_title": r["english_title"],
            "category": r.get("category", "other"),
            "relevance": r.get("relevance", 0),
            "published_at": r.get("published_at", "")[:10],
            "similarity_score": r["score"],
        })
        if len(articles) >= limit:
            break

    return {
        "articles": articles,
        "total": len(articles),
        "has_more": len(results) > len(articles),
        "query": query,
    }


# ── Tool 2: Get Latest Briefing ────────────────────────────

@mcp.tool
def lex_get_briefing(
    date: Optional[str] = None,
) -> dict:
    """Get the latest Chinese AI morning briefing (Bloomberg-style).

    Use this when you need a summary of what happened in Chinese AI/tech
    today or on a specific date. The briefing has five sections:
    LEAD (biggest story), PATTERNS (cross-source themes), SIGNALS
    (emerging trends), WATCHLIST (developing stories), DATA (key numbers).

    Args:
        date: ISO date string (YYYY-MM-DD) to fetch a specific day's
              briefing. Omit for the most recent briefing.

    Returns dict with 'briefing' text, 'date', 'article_count', 'model_used'.
    Returns empty briefing if none exists for the requested date.
    """
    from lib.db import _get_client

    client = _get_client()

    query = client.table("briefings") \
        .select("briefing_text, article_count, model_used, created_at") \
        .order("created_at", desc=True)

    if date:
        query = query.gte("created_at", f"{date}T00:00:00Z") \
                     .lt("created_at", f"{date}T23:59:59Z")

    result = query.limit(1).execute()

    if not result.data:
        return {
            "briefing": "",
            "date": date or "none",
            "article_count": 0,
            "message": "No briefing found. Try omitting the date for the latest.",
        }

    row = result.data[0]
    return {
        "briefing": row["briefing_text"],
        "date": row["created_at"][:10],
        "article_count": row["article_count"],
        "model_used": row["model_used"],
    }


# ── Tool 3: Get Signals ────────────────────────────────────

@mcp.tool
def lex_get_signals(
    days: int = 7,
    min_relevance: int = 4,
) -> dict:
    """Get emerging signals and high-relevance developments from recent days.

    Use this to understand what trends are building in Chinese AI/tech.
    Returns articles scored 4+ (significant) or 5 (critical) from the
    last N days, grouped by category.

    Args:
        days: Lookback window in days (1-30, default 7)
        min_relevance: Minimum relevance score (default 4 = significant+)

    Returns dict with 'signals' grouped by category, 'total', 'period'.
    """
    from lib.db import _get_client

    client = _get_client()
    days = max(1, min(days, 30))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    result = client.table("articles") \
        .select("source, english_title, category, relevance, published_at") \
        .gte("relevance", min_relevance) \
        .gte("scraped_at", cutoff) \
        .order("relevance", desc=True) \
        .order("scraped_at", desc=True) \
        .limit(50) \
        .execute()

    # Cluster articles into signal threads by category + shared keywords
    import re as _re
    _stop = {"the", "a", "an", "in", "of", "to", "for", "and", "is", "on",
             "at", "by", "with", "from", "its", "has", "new", "china", "chinese",
             "ai", "says", "will", "than", "more", "about", "into", "over"}

    def _keywords(title):
        words = set(_re.findall(r'[a-z]{3,}', (title or "").lower()))
        return words - _stop

    clusters = []  # each: {theme, category, sources, articles, confidence}
    used = set()

    for i, a in enumerate(result.data):
        if i in used:
            continue
        kw_a = _keywords(a.get("english_title", ""))
        group = [a]
        used.add(i)

        for j, b in enumerate(result.data):
            if j in used:
                continue
            kw_b = _keywords(b.get("english_title", ""))
            shared = kw_a & kw_b
            same_cat = a.get("category") == b.get("category")
            if len(shared) >= 2 and same_cat:
                group.append(b)
                used.add(j)
                kw_a = kw_a | kw_b  # widen for transitive matches

        sources = list({x["source"] for x in group})
        n = len(sources)
        confidence = "high" if n >= 3 else ("medium" if n >= 2 else "single-source")

        # Build theme from most common keywords
        all_kw = _keywords(" ".join(x.get("english_title", "") for x in group))
        theme = group[0].get("english_title", "")[:80]

        clusters.append({
            "theme": theme,
            "category": a.get("category", "other"),
            "source_count": n,
            "sources": sources,
            "confidence": confidence,
            "articles": [{
                "source": x["source"],
                "english_title": x.get("english_title", ""),
                "relevance": x["relevance"],
                "published_at": (x.get("published_at") or "")[:10],
            } for x in group],
        })

    clusters.sort(key=lambda c: (-c["source_count"], -max(a["relevance"] for a in c["articles"])))

    return {
        "signals": clusters,
        "total": len(result.data),
        "signal_count": len(clusters),
        "period": f"last {days} days",
        "min_relevance": min_relevance,
    }


# ── Tool 4: List Sources ───────────────────────────────────

@mcp.tool
def lex_list_sources() -> dict:
    """List all Chinese AI/tech sources Lex monitors and their health.

    Use this to understand what data sources feed the intelligence pipeline
    and how recently each was successfully scraped.

    Returns dict with 'sources' list. Each source has: name, last_seen,
    article_count_30d, signal_quality_pct.
    """
    from lib.db import _get_client

    client = _get_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    articles = client.table("articles") \
        .select("source, relevance") \
        .gte("scraped_at", cutoff) \
        .execute()

    # Aggregate per source
    stats = {}
    for a in articles.data:
        src = a["source"]
        if src not in stats:
            stats[src] = {"total": 0, "high": 0}
        stats[src]["total"] += 1
        if (a.get("relevance") or 0) >= 4:
            stats[src]["high"] += 1

    # Get last scrape time per source
    latest_run = client.table("scrape_runs") \
        .select("sources_ok, finished_at") \
        .order("finished_at", desc=True) \
        .limit(1) \
        .execute()

    if latest_run.data and latest_run.data[0].get("finished_at"):
        last_scrape = latest_run.data[0]["finished_at"][:16]
    else:
        last_scrape = "unknown"

    sources = []
    for src, s in sorted(stats.items(), key=lambda x: -x[1]["total"]):
        pct = round(100 * s["high"] / s["total"], 1) if s["total"] else 0
        sources.append({
            "name": src,
            "article_count_30d": s["total"],
            "high_relevance_count": s["high"],
            "signal_quality_pct": pct,
        })

    return {
        "sources": sources,
        "total_sources": len(sources),
        "last_scrape": last_scrape,
    }


# ── Tool 5: Get Trending Categories ────────────────────────

@mcp.tool
def lex_get_trending(
    days: int = 7,
) -> dict:
    """Get trending categories and topic momentum in Chinese AI/tech.

    Use this to understand which areas of Chinese AI are seeing the most
    activity. Compares recent article volume by category to the previous
    period to show momentum (growing vs declining coverage).

    Args:
        days: Analysis window in days (1-30, default 7).
              Compares this period vs the prior equivalent period.

    Returns dict with 'categories' showing current count, previous count,
    and momentum direction.
    """
    from lib.db import _get_client

    client = _get_client()
    days = max(1, min(days, 30))
    now = datetime.now(timezone.utc)
    current_start = (now - timedelta(days=days)).isoformat()
    prev_start = (now - timedelta(days=days * 2)).isoformat()

    current = client.table("articles") \
        .select("category") \
        .gte("scraped_at", current_start) \
        .execute()

    previous = client.table("articles") \
        .select("category") \
        .gte("scraped_at", prev_start) \
        .lt("scraped_at", current_start) \
        .execute()

    cur_counts = {}
    for a in current.data:
        cat = a.get("category", "other")
        cur_counts[cat] = cur_counts.get(cat, 0) + 1

    prev_counts = {}
    for a in previous.data:
        cat = a.get("category", "other")
        prev_counts[cat] = prev_counts.get(cat, 0) + 1

    all_cats = set(cur_counts) | set(prev_counts)
    categories = []
    for cat in sorted(all_cats):
        cur = cur_counts.get(cat, 0)
        prev = prev_counts.get(cat, 0)
        if prev > 0:
            change_pct = round(100 * (cur - prev) / prev, 1)
        elif cur > 0:
            change_pct = 100.0
        else:
            change_pct = 0.0

        if change_pct > 10:
            momentum = "rising"
        elif change_pct < -10:
            momentum = "declining"
        else:
            momentum = "stable"

        categories.append({
            "category": cat,
            "current_period": cur,
            "previous_period": prev,
            "change_pct": change_pct,
            "momentum": momentum,
        })

    categories.sort(key=lambda x: x["current_period"], reverse=True)

    return {
        "categories": categories,
        "period": f"{days}-day windows",
        "current_articles": len(current.data),
        "previous_articles": len(previous.data),
    }


# ── Tool 6: Get Article Detail ──────────────────────────────

@mcp.tool
def lex_get_article(
    article_id: str,
) -> dict:
    """Get full details of a specific article by its ID.

    Use this after finding articles via lex_search_articles or
    lex_get_signals to retrieve the full body text and metadata.

    Args:
        article_id: The Pinecone record ID (from search results) or
                    Supabase UUID.

    Returns dict with full article details including body text.
    If not found, returns an error message.
    """
    from lib.db import _get_client

    client = _get_client()

    # Try Supabase UUID first
    result = client.table("articles") \
        .select("*") \
        .eq("id", article_id) \
        .limit(1) \
        .execute()

    if not result.data:
        # Try source_id (Pinecone hash ID)
        result = client.table("articles") \
            .select("*") \
            .eq("source_id", article_id) \
            .limit(1) \
            .execute()

    if not result.data:
        return {"error": f"Article '{article_id}' not found. Use lex_search_articles to find valid IDs."}

    a = result.data[0]
    return {
        "id": a["id"],
        "source": a["source"],
        "title": a["title"],
        "english_title": a.get("english_title", ""),
        "body": (a.get("body") or "")[:3000],
        "category": a.get("category", "other"),
        "relevance": a.get("relevance"),
        "published_at": a.get("published_at"),
        "url": a.get("url"),
        "status": a.get("status"),
    }


# ── Tool 7: Get Pipeline Status ───────────────────────────

@mcp.tool
def lex_get_status() -> dict:
    """Get current pipeline health — latest scrape run, article counts, publish queue.

    Use this to check if overnight runs succeeded, if articles are waiting
    for analysis, or if the publish queue has failures.

    Returns dict with 'latest_run', 'articles' counts, 'publish_queue' counts.
    """
    from lib.db import _get_client

    client = _get_client()

    latest = client.table("scrape_runs") \
        .select("*") \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    pending = client.table("articles") \
        .select("id", count="exact") \
        .eq("status", "pending") \
        .execute()

    analyzed = client.table("articles") \
        .select("id", count="exact") \
        .eq("status", "analyzed") \
        .execute()

    queued = client.table("publish_queue") \
        .select("id", count="exact") \
        .eq("status", "queued") \
        .execute()

    retry = client.table("publish_queue") \
        .select("id", count="exact") \
        .eq("status", "retry_queued") \
        .execute()

    failed = client.table("publish_queue") \
        .select("id", count="exact") \
        .eq("status", "failed") \
        .execute()

    published_today = client.table("publish_queue") \
        .select("id", count="exact") \
        .eq("status", "published") \
        .gte("published_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")) \
        .execute()

    return {
        "latest_run": latest.data[0] if latest.data else None,
        "articles": {
            "pending": pending.count,
            "analyzed": analyzed.count,
        },
        "publish_queue": {
            "queued": queued.count,
            "retry_queued": retry.count,
            "failed": failed.count,
            "published_today": published_today.count,
        },
    }


# ── Tool 8: Run Scrape (WRITE) ───────────────────────────

@mcp.tool
def lex_run_scrape() -> dict:
    """Scrape all 11 Chinese AI sources and Gmail newsletters for new articles.

    WRITE OPERATION: Fetches articles from external sites, deduplicates against
    Supabase history, and inserts new articles with status 'pending'. Also
    records scrape run metadata. No arguments needed.

    Returns dict with 'found' (total fetched), 'new' (after dedup),
    'sources_ok' (successful sources), 'sources_failed' (failed sources).
    """
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    from lib.scrape import run_scrape
    return run_scrape()


# ── Tool 9: Run Analyze (WRITE) ──────────────────────────

@mcp.tool
def lex_run_analyze(
    model: str = "sonnet",
) -> dict:
    """Analyze pending articles: translate, categorize, generate briefing and post drafts.

    WRITE OPERATION: Reads pending articles from Supabase, runs two-stage LLM
    pipeline (Stage 1: translate + categorize + score relevance, Stage 2:
    cross-source pattern analysis + briefing + post drafts), updates article
    statuses, inserts briefing, and queues posts for publishing.

    Args:
        model: LLM model tier to use. 'sonnet' (default, ~$0.05-0.15/run)
               or 'opus' (~$0.30-0.60/run, higher quality analysis).

    Returns dict with 'analyzed', 'relevant', 'briefing_id', 'drafts', 'posts_queued'.
    """
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    from lib.analyze import run_analyze

    model_map = {
        "sonnet": "claude-sonnet-4-20250514",
        "opus": "claude-opus-4-20250514",
    }
    model_id = model_map.get(model, model_map["sonnet"])
    return run_analyze(model=model_id)


# ── Tool 10: Run Publish (WRITE) ─────────────────────────

@mcp.tool
def lex_run_publish(
    platform: Optional[str] = None,
) -> dict:
    """Drain the publish queue to configured platforms (LinkedIn, Dev.to, Medium).

    WRITE OPERATION: Reads queued posts from Supabase and publishes them via
    platform APIs. Handles retries with exponential backoff (5m/20m/80m).
    Falls back to simplified content if full post fails. Posts to platforms
    without configured API keys are silently skipped.

    Args:
        platform: Publish to a specific platform only. One of: 'linkedin',
                  'devto', 'medium'. Omit to publish to all configured platforms.

    Returns dict with 'published', 'failed', 'skipped' counts.
    """
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    from lib.publish import drain_queue
    return drain_queue(platform=platform)


# ── Tool 11: Run Full Cycle (WRITE) ──────────────────────

@mcp.tool
def lex_run_cycle() -> dict:
    """Run the full pipeline: scrape all sources, analyze new articles, publish posts.

    WRITE OPERATION: Executes all three phases sequentially:
    Phase 1 (Scrape): Fetch from 11 sources + Gmail, dedup, insert new articles.
    Phase 2 (Analyze): Translate, categorize, score, generate briefing + drafts.
    Phase 3 (Publish): Drain publish queue to all configured platforms.
    If Phase 1 finds no new articles, Phases 2 and 3 are skipped.

    Returns dict with 'scrape', 'analyze', 'publish' sub-results,
    or just 'scrape' if no new articles were found.
    """
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    log = logging.getLogger("lex.cycle")

    from lib.scrape import run_scrape
    from lib.analyze import run_analyze
    from lib.publish import drain_queue

    log.info("Phase 1: Scraping sources...")
    scrape_result = run_scrape()
    log.info("Scrape: %d found, %d new", scrape_result["found"], scrape_result["new"])

    if scrape_result["new"] == 0:
        log.info("No new articles, skipping analysis and publish")
        return {"scrape": scrape_result, "skipped": "no new articles"}

    log.info("Phase 2: Analyzing articles...")
    analyze_result = run_analyze()
    log.info("Analyze: %d analyzed, %d posts queued", analyze_result["analyzed"], analyze_result["posts_queued"])

    log.info("Phase 3: Publishing posts...")
    publish_result = drain_queue()
    log.info("Publish: %d published, %d failed", publish_result["published"], publish_result["failed"])

    return {
        "scrape": scrape_result,
        "analyze": analyze_result,
        "publish": publish_result,
    }


# ── Multi-Agent Tools ─────────────────────────────────────

@mcp.tool
def lex_store_research(
    title: str,
    body: str,
    source: str,
    category: str = "general",
    relevance: int = 3,
    source_url: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Store a research item from the Scout agent.

    WRITE OPERATION: Inserts a new research item into the research_items
    table with optional embedding for vector search.

    Args:
        title: Research item title
        body: Full text content
        source: Where this came from (e.g., 'sam_gov', 'rss', 'web_search')
        category: Category (e.g., 'opportunity', 'technology', 'market', 'contract')
        relevance: Relevance score 1-5
        source_url: URL of the source (optional)
        metadata: Additional metadata as JSON (optional)

    Returns dict with 'id' of the created research item.
    """
    from lib.db import _get_client
    from lib.vectors import embed_text

    client = _get_client()
    embedding = embed_text(f"{title}\n\n{body[:2000]}")

    row = {
        "title": title,
        "body": body,
        "source": source,
        "category": category,
        "relevance": relevance,
        "source_url": source_url,
        "metadata": metadata or {},
    }
    if embedding:
        row["embedding"] = embedding

    result = client.table("research_items").insert(row).execute()
    return {"id": result.data[0]["id"], "embedded": embedding is not None}


@mcp.tool
def lex_store_analysis(
    report_type: str,
    title: str,
    body: str,
    confidence: float = 0.5,
    source_items: Optional[list] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Store an analysis report from the Analyst agent.

    WRITE OPERATION: Inserts a new analysis report.

    Args:
        report_type: Type of report ('trend', 'anomaly', 'briefing', 'pattern')
        title: Report title
        body: Full report text
        confidence: Confidence score 0.0-1.0
        source_items: List of source item UUIDs that this report is based on
        metadata: Additional metadata

    Returns dict with 'id' of the created report.
    """
    from lib.db import _get_client

    client = _get_client()
    result = client.table("analysis_reports").insert({
        "report_type": report_type,
        "title": title,
        "body": body,
        "confidence": confidence,
        "source_items": source_items or [],
        "metadata": metadata or {},
    }).execute()
    return {"id": result.data[0]["id"]}


@mcp.tool
def lex_store_opportunity(
    title: str,
    description: str,
    opp_type: str,
    priority: int = 3,
    estimated_value: Optional[str] = None,
    deadline: Optional[str] = None,
    source_reports: Optional[list] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Store an opportunity from the Strategist agent.

    WRITE OPERATION: Inserts a new opportunity assessment.

    Args:
        title: Opportunity title
        description: Full description
        opp_type: Type ('contract', 'product', 'partnership', 'content', 'grant')
        priority: Priority 1-5 (1=highest)
        estimated_value: Estimated value (e.g., '$10K-50K', 'recurring $2K/mo')
        deadline: Deadline date as ISO string (YYYY-MM-DD)
        source_reports: List of analysis report UUIDs this is based on
        metadata: Additional metadata

    Returns dict with 'id' of the created opportunity.
    """
    from lib.db import _get_client

    client = _get_client()
    row = {
        "title": title,
        "description": description,
        "opp_type": opp_type,
        "priority": priority,
        "estimated_value": estimated_value,
        "source_reports": source_reports or [],
        "metadata": metadata or {},
    }
    if deadline:
        row["deadline"] = deadline

    result = client.table("opportunities").insert(row).execute()
    return {"id": result.data[0]["id"]}


@mcp.tool
def lex_store_action_item(
    title: str,
    description: str,
    action_type: str,
    priority: int = 3,
    deadline: Optional[str] = None,
    deliverable: Optional[str] = None,
    requires_human: bool = False,
    source_reports: Optional[list] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Store an action item from the Executor agent.

    WRITE OPERATION: Inserts a new action item.

    Args:
        title: Action item title
        description: What needs to be done
        action_type: Type ('proposal', 'content', 'outreach', 'invoice', 'follow_up', 'technical')
        priority: Priority 1-5 (1=highest)
        deadline: Deadline as ISO date (YYYY-MM-DD)
        deliverable: What the output should be
        requires_human: Whether human approval is needed before execution
        source_reports: List of report UUIDs this stems from
        metadata: Additional metadata

    Returns dict with 'id' of the created action item.
    """
    from lib.db import _get_client

    client = _get_client()
    row = {
        "title": title,
        "description": description,
        "action_type": action_type,
        "priority": priority,
        "deliverable": deliverable,
        "requires_human": requires_human,
        "source_reports": source_reports or [],
        "metadata": metadata or {},
    }
    if deadline:
        row["deadline"] = deadline

    result = client.table("action_items").insert(row).execute()
    return {"id": result.data[0]["id"]}


@mcp.tool
def lex_get_pending_actions(
    status: str = "pending",
    requires_human: Optional[bool] = None,
    limit: int = 20,
) -> dict:
    """Get action items by status, optionally filtered to human-required items.

    Use this to check what actions are pending, which need human approval,
    or what has been completed.

    Args:
        status: Filter by status ('pending', 'in_progress', 'blocked', 'completed', 'cancelled')
        requires_human: If True, only items needing human approval. If False, only automated. Omit for all.
        limit: Max results (1-100, default 20)

    Returns dict with 'items' list and 'total' count.
    """
    from lib.db import _get_client

    client = _get_client()
    limit = max(1, min(limit, 100))

    query = client.table("action_items") \
        .select("*") \
        .eq("status", status) \
        .order("priority") \
        .order("created_at", desc=True) \
        .limit(limit)

    if requires_human is not None:
        query = query.eq("requires_human", requires_human)

    result = query.execute()

    return {
        "items": result.data,
        "total": len(result.data),
        "filter": {"status": status, "requires_human": requires_human},
    }


@mcp.tool
def lex_get_opportunities(
    status: str = "identified",
    opp_type: Optional[str] = None,
    min_priority: int = 5,
    limit: int = 20,
) -> dict:
    """Get opportunities by status and type.

    Use this to review identified opportunities, track which are being
    pursued, or find high-priority items.

    Args:
        status: Filter by status ('identified', 'evaluating', 'pursuing', 'won', 'lost', 'declined')
        opp_type: Filter by type ('contract', 'product', 'partnership', 'content', 'grant'). Omit for all.
        min_priority: Maximum priority number to include (1=highest, 5=lowest). Default 5 (all).
        limit: Max results (1-100, default 20)

    Returns dict with 'opportunities' list and 'total' count.
    """
    from lib.db import _get_client

    client = _get_client()
    limit = max(1, min(limit, 100))

    query = client.table("opportunities") \
        .select("*") \
        .eq("status", status) \
        .lte("priority", min_priority) \
        .order("priority") \
        .order("created_at", desc=True) \
        .limit(limit)

    if opp_type:
        query = query.eq("opp_type", opp_type)

    result = query.execute()

    return {
        "opportunities": result.data,
        "total": len(result.data),
    }


@mcp.tool
def lex_log_agent_run(
    agent_id: str,
    status: str,
    run_type: str = "scheduled",
    items_processed: int = 0,
    items_created: int = 0,
    duration_s: Optional[float] = None,
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Log an agent run to the agent_runs table.

    WRITE OPERATION: Records agent execution metadata for monitoring.

    Args:
        agent_id: Which agent ran ('scout', 'analyst', 'strategist', 'synthesizer', 'executor', 'chief', 'email')
        status: Run status ('started', 'completed', 'failed', 'timeout')
        run_type: Type of run ('scheduled', 'triggered', 'manual')
        items_processed: Number of items the agent processed
        items_created: Number of new items the agent created
        duration_s: How long the run took in seconds
        error: Error message if failed
        metadata: Additional run metadata

    Returns dict with 'id' of the agent run log entry.
    """
    from lib.db import _get_client

    client = _get_client()
    row = {
        "agent_id": agent_id,
        "status": status,
        "run_type": run_type,
        "items_processed": items_processed,
        "items_created": items_created,
        "metadata": metadata or {},
    }
    if duration_s is not None:
        row["duration_s"] = duration_s
    if error:
        row["error"] = error
    if status in ("completed", "failed", "timeout"):
        row["finished_at"] = datetime.now(timezone.utc).isoformat()

    result = client.table("agent_runs").insert(row).execute()
    return {"id": result.data[0]["id"]}


@mcp.tool
def lex_vector_search(
    query: str,
    table: str = "articles",
    limit: int = 10,
    min_similarity: float = 0.5,
    days: Optional[int] = None,
) -> dict:
    """Semantic vector search across articles or research items using pgvector.

    Use this for finding semantically related content across the knowledge base.
    More powerful than lex_search_articles as it searches the local pgvector
    database directly instead of requiring Pinecone.

    Args:
        query: Natural language search query
        table: Which table to search ('articles' or 'research_items')
        limit: Max results (1-50, default 10)
        min_similarity: Minimum cosine similarity threshold (0.0-1.0, default 0.5)
        days: Only search items from the last N days (optional)

    Returns dict with 'results' list containing matched items with similarity scores.
    """
    from lib.vectors import vector_search

    limit = max(1, min(limit, 50))
    results = vector_search(
        query_text=query,
        table=table,
        limit=limit,
        min_similarity=min_similarity,
        filters={"days": days} if days else None,
    )

    return {
        "results": results,
        "total": len(results),
        "query": query,
        "table": table,
    }


@mcp.tool
def lex_get_daily_digest() -> dict:
    """Generate a daily digest of all agent activity for the Chief agent.

    Summarizes: what each agent did today, pending action items needing
    human attention, opportunities identified, and pipeline health.

    Returns dict with sections for each area of activity.
    """
    from lib.db import _get_client

    client = _get_client()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")

    # Today's agent runs
    runs = client.table("agent_runs") \
        .select("agent_id, status, items_processed, items_created, duration_s, error") \
        .gte("started_at", today) \
        .order("started_at", desc=True) \
        .execute()

    # Pending human-required actions
    human_actions = client.table("action_items") \
        .select("title, action_type, priority, deadline") \
        .eq("requires_human", True) \
        .eq("status", "pending") \
        .order("priority") \
        .limit(10) \
        .execute()

    # New opportunities today
    new_opps = client.table("opportunities") \
        .select("title, opp_type, priority, estimated_value") \
        .gte("created_at", today) \
        .order("priority") \
        .execute()

    # Pipeline status
    pending_articles = client.table("articles") \
        .select("id", count="exact") \
        .eq("status", "pending") \
        .execute()

    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "agent_activity": runs.data,
        "needs_your_attention": human_actions.data,
        "new_opportunities": new_opps.data,
        "pipeline": {
            "articles_pending": pending_articles.count,
        },
    }


if __name__ == "__main__":
    mcp.run()
