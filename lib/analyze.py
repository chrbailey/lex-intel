"""
Lex analyze module — runs Ahgen's two-stage LLM pipeline against Supabase articles.

Stage 1: Translate Chinese titles → English, categorize, score relevance 1-5
Stage 2: Cross-source pattern analysis → LEAD/PATTERNS/SIGNALS/WATCHLIST/DATA briefing
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import anthropic

from lib.db import (
    get_pending_articles,
    update_article_enrichment,
    mark_articles_status,
    insert_briefing,
    enqueue_post,
    start_scrape_run,
    finish_scrape_run,
)

# Reuse Ahgen's LLM functions directly
import sys
AHGEN_DIR = Path("/Volumes/OWC drive/Dev/ahgen")
if str(AHGEN_DIR) not in sys.path:
    sys.path.insert(0, str(AHGEN_DIR))

from ahgen import (
    stage1_translate_categorize,
    stage2_pattern_analysis,
    load_prompts,
    retry_with_backoff,
)

log = logging.getLogger("lex.analyze")


def _get_client() -> anthropic.Anthropic:
    """Get Anthropic client from env."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=api_key)


def _extract_lead(briefing_text: str) -> Optional[str]:
    """Extract the LEAD paragraph from a briefing for use as fallback_body."""
    if not briefing_text:
        return None
    # LEAD is typically the first paragraph or section
    for section in briefing_text.split("\n\n"):
        section = section.strip()
        if section and not section.startswith("#"):
            return section[:500]
    return briefing_text[:500]


def run_analyze(model: str = "claude-sonnet-4-20250514") -> Dict:
    """Full analyze cycle: read pending articles → enrich → briefing → queue posts.

    Returns summary dict.
    """
    run_id = start_scrape_run(mode="analyze")
    log.info(f"Analyze run {run_id} started")

    # Get pending articles from Supabase
    articles = get_pending_articles(limit=500)
    if not articles:
        log.info("No pending articles to analyze")
        finish_scrape_run(run_id, 0, 0, [], [])
        return {"run_id": run_id, "analyzed": 0, "briefing": False}

    log.info(f"Analyzing {len(articles)} pending articles")

    client = _get_client()
    system_prompt = load_prompts()

    # Stage 1: Translate, categorize, score
    log.info("Stage 1: Translating and categorizing...")

    # Convert Supabase rows to Ahgen's expected format
    ahgen_articles = []
    id_map = {}  # index → supabase article id
    for i, a in enumerate(articles):
        ahgen_articles.append({
            "source": a["source"],
            "title": a["title"],
            "subject": a["title"],
            "body": a.get("body") or "",
            "content": a.get("body") or "",
            "date": a.get("published_at") or a["scraped_at"],
            "url": a.get("url") or "",
        })
        id_map[i] = a["id"]

    enriched = stage1_translate_categorize(client, ahgen_articles)
    log.info(f"Stage 1 complete: {len(enriched)} enriched")

    # Write enrichment back to Supabase
    for i, e in enumerate(enriched):
        if i in id_map:
            update_article_enrichment(
                id_map[i],
                english_title=e.get("english_title", ""),
                category=e.get("category", "other"),
                relevance=e.get("relevance", 1),
            )

    # Filter to relevance >= 3
    relevant = [e for e in enriched if e.get("relevance", 1) >= 3]
    log.info(f"Relevance filter: {len(enriched)} -> {len(relevant)} (score >= 3)")

    briefing_text = ""
    drafts = []

    if relevant:
        # Stage 2: Pattern analysis + briefing generation
        log.info("Stage 2: Pattern analysis and briefing generation...")
        result = stage2_pattern_analysis(client, system_prompt, relevant)
        briefing_text = result.get("briefing", "")
        drafts = result.get("drafts", [])
        log.info(f"Stage 2 complete: {len(briefing_text)} char briefing, {len(drafts)} drafts")

    # Insert briefing into Supabase
    briefing_id = None
    if briefing_text:
        briefing_id = insert_briefing(
            briefing_text=briefing_text,
            article_count=len(relevant),
            model_used=model,
            scrape_run_id=run_id,
        )
        log.info(f"Briefing {briefing_id} saved")

    # Queue posts for publishing
    lead_text = _extract_lead(briefing_text)
    posts_queued = 0

    for draft in drafts:
        urgency = draft.get("urgency", "medium")
        source = draft.get("source", "unknown")

        # Global post → LinkedIn + Dev.to
        global_post = draft.get("global_post") or draft.get("global_draft") or {}
        if global_post.get("text"):
            for platform in ["linkedin", "devto"]:
                title = draft.get("english_title") or draft.get("summary") or ""
                enqueue_post(
                    platform=platform,
                    body=global_post["text"],
                    title=title if platform == "devto" else None,
                    urgency=urgency,
                    language="en",
                    fallback_body=lead_text,
                    briefing_id=briefing_id,
                )
                posts_queued += 1

        # China post → LinkedIn (Chinese audience)
        china_post = draft.get("china_post") or draft.get("china_draft") or {}
        if china_post.get("text"):
            enqueue_post(
                platform="linkedin",
                body=china_post["text"],
                urgency=urgency,
                language="zh",
                fallback_body=lead_text,
                briefing_id=briefing_id,
            )
            posts_queued += 1

    log.info(f"Queued {posts_queued} posts for publishing")

    # Mark all analyzed articles
    all_ids = [a["id"] for a in articles]
    mark_articles_status(all_ids, "analyzed")

    finish_scrape_run(
        run_id,
        articles_found=len(articles),
        articles_new=len(relevant),
        sources_ok=["analyze_pipeline"],
        sources_failed=[],
    )

    return {
        "run_id": run_id,
        "analyzed": len(articles),
        "relevant": len(relevant),
        "briefing_id": briefing_id,
        "drafts": len(drafts),
        "posts_queued": posts_queued,
    }
