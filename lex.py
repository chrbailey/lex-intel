#!/usr/bin/env python3
"""
Lex — Chinese AI Intelligence Pipeline

Wraps Ahgen's scraping + analysis pipeline with Supabase persistence
and multi-platform publishing.

Modes:
  lex.py scrape          Scrape all sources → dedup → insert to Supabase
  lex.py analyze         Read pending articles → enrich → briefing → queue posts
  lex.py publish         Drain publish queue to configured platforms
  lex.py cycle           Full pipeline: scrape → analyze → publish
  lex.py status          Show latest scrape run + queue stats
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load .env
ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("lex")


def cmd_scrape():
    """Run scrape cycle."""
    from lib.scrape import run_scrape
    result = run_scrape()
    print(json.dumps(result, indent=2, default=str))


def cmd_analyze():
    """Run analyze cycle."""
    from lib.analyze import run_analyze
    model = "claude-sonnet-4-20250514"
    if "--opus" in sys.argv:
        model = "claude-opus-4-20250514"
    result = run_analyze(model=model)
    print(json.dumps(result, indent=2, default=str))


def cmd_publish():
    """Drain publish queue."""
    from lib.publish import drain_queue
    platform = None
    for arg in sys.argv[2:]:
        if not arg.startswith("--"):
            platform = arg
    result = drain_queue(platform=platform)
    print(json.dumps(result, indent=2, default=str))


def cmd_cycle():
    """Full pipeline: scrape → analyze → publish."""
    log.info("=== Lex full cycle started ===")

    from lib.scrape import run_scrape
    from lib.analyze import run_analyze
    from lib.publish import drain_queue

    # 1. Scrape
    log.info("Phase 1: Scraping sources...")
    scrape_result = run_scrape()
    log.info(f"Scrape: {scrape_result['found']} found, {scrape_result['new']} new")

    if scrape_result["new"] == 0:
        log.info("No new articles, skipping analysis")
        return

    # 2. Analyze
    log.info("Phase 2: Analyzing articles...")
    analyze_result = run_analyze()
    log.info(f"Analyze: {analyze_result['analyzed']} analyzed, {analyze_result['posts_queued']} posts queued")

    # 3. Publish
    log.info("Phase 3: Publishing posts...")
    publish_result = drain_queue()
    log.info(f"Publish: {publish_result['published']} published, {publish_result['failed']} failed")

    log.info("=== Lex full cycle complete ===")
    print(json.dumps({
        "scrape": scrape_result,
        "analyze": analyze_result,
        "publish": publish_result,
    }, indent=2, default=str))


def cmd_status():
    """Show current status — latest run, queue depths, health."""
    from lib.db import _get_client

    client = _get_client()

    # Latest scrape run
    latest = client.table("scrape_runs") \
        .select("*") \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    # Article counts by status
    pending = client.table("articles") \
        .select("id", count="exact") \
        .eq("status", "pending") \
        .execute()

    analyzed = client.table("articles") \
        .select("id", count="exact") \
        .eq("status", "analyzed") \
        .execute()

    # Publish queue by status
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

    status = {
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

    print(json.dumps(status, indent=2, default=str))


def cmd_search():
    """Semantic search across article corpus via Pinecone."""
    from lib.vectors import search
    query = " ".join(a for a in sys.argv[2:] if not a.startswith("--"))
    if not query:
        print("Usage: lex.py search \"query\" [--top=10]")
        sys.exit(1)
    top_k = 10
    for arg in sys.argv[2:]:
        if arg.startswith("--top="):
            top_k = int(arg.split("=")[1])
    results = search(query, top_k=top_k)
    if not results:
        print("No results found.")
        return
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r['source']}] {r['english_title']}")
        print(f"   Score: {r['score']}  Category: {r['category']}  Relevance: {r['relevance']}  Date: {r['published_at'][:10]}")


def cmd_patterns():
    """Show pipeline analytics."""
    from lib.db import get_analytics
    days = 30
    for arg in sys.argv[2:]:
        if arg.startswith("--days="):
            days = int(arg.split("=")[1])
    stats = get_analytics(days=days)
    print(f"\n=== Lex Pipeline Analytics ({days} days) ===\n")
    print(f"Total articles: {stats['articles_total']}")
    print(f"\n--- Source Signal Quality ---")
    for src, q in stats["source_quality"].items():
        print(f"  {src:20s}  {q['total']:4d} articles  {q['high_relevance']:3d} high-rel  {q['signal_pct']:5.1f}%")
    print(f"\n--- Category Distribution ---")
    for cat, count in stats["category_distribution"].items():
        pct = round(100 * count / stats["articles_total"], 1) if stats["articles_total"] else 0
        print(f"  {cat:20s}  {count:4d}  ({pct:.1f}%)")
    print(f"\n--- Publish Stats ---")
    for plat, ps in stats["publish_stats"].items():
        rate = round(100 * ps["published"] / ps["total"], 1) if ps["total"] else 0
        print(f"  {plat:12s}  {ps['total']:3d} total  {ps['published']:3d} published  {ps['failed']:3d} failed  ({rate:.1f}% success)")
    print(f"\n--- Briefings ---")
    print(f"  Total: {stats['briefings']['total']}  Emailed: {stats['briefings']['emailed']}")


def cmd_cleanup():
    """Maintenance: archive old articles + clean dedup table."""
    from lib.db import archive_old_articles, cleanup_dedup
    days = 30
    for arg in sys.argv[2:]:
        if arg.startswith("--days="):
            days = int(arg.split("=")[1])
    archived = archive_old_articles(days=days)
    cleaned = cleanup_dedup(days=days)
    print(f"Archived {archived} articles older than {days} days")
    print(f"Cleaned {cleaned} dedup entries older than {days} days")


COMMANDS = {
    "scrape": cmd_scrape,
    "analyze": cmd_analyze,
    "publish": cmd_publish,
    "cycle": cmd_cycle,
    "status": cmd_status,
    "search": cmd_search,
    "patterns": cmd_patterns,
    "cleanup": cmd_cleanup,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"Commands: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
