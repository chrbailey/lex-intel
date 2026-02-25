"""
Lex analyze module — two-stage LLM pipeline with Pinecone integration.

Stage 1: Translate Chinese titles -> English, categorize (13 categories), score relevance 1-5
Stage 2: Cross-source pattern analysis -> LEAD/PATTERNS/SIGNALS/WATCHLIST/DATA briefing
         with historical context from Pinecone

Prompts are loaded from prompts/ directory (decoupled from Ahgen).
Utilities (retry_with_backoff, _parse_claude_json) are still imported from Ahgen.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from lib.db import (
    get_pending_articles,
    update_article_enrichment,
    mark_articles_status,
    insert_briefing,
    enqueue_post,
    start_scrape_run,
    finish_scrape_run,
)
from lib.vectors import upsert_articles, get_historical_context

log = logging.getLogger("lex.analyze")

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
MAX_RETRIES = 3
RETRY_DELAY = 5


# ── Utilities (local copies, no Ahgen dependency) ──────────

def _retry_with_backoff(func, *args, **kwargs) -> Any:
    """Retry a function with exponential backoff on transient errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except (
            httpx.NetworkError,
            httpx.TimeoutException,
            ConnectionError,
            OSError,
        ) as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = RETRY_DELAY * (2 ** attempt)
            log.warning(f"Transient error, retrying in {wait}s: {e}")
            time.sleep(wait)
    return None


def _parse_claude_json(response_text: str) -> Any:
    """Extract and parse JSON from Claude response, handling markdown wrapping."""
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        parts = response_text.split("```")
        if len(parts) >= 2:
            response_text = parts[1]

    response_text = response_text.strip()
    response_text = re.sub(r',(\s*[}\]])', r'\1', response_text)

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{[\s\S]*\}', response_text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    log.warning(f"Could not parse JSON. Response (first 1000 chars):\n{response_text[:1000]}")
    return None


# ── LLM Completion (Agent SDK / API fallback) ──────────────


async def _agent_sdk_complete(prompt: str) -> str:
    """Call Claude via Agent SDK (Max subscription)."""
    from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

    chunks = []  # type: List[str]
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=[],
            max_turns=1,
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    chunks.append(block.text)
    return "".join(chunks)


def _llm_complete(prompt: str, max_tokens: int = 4096) -> str:
    """Call Claude via Agent SDK using Max subscription.

    Uses the same auth as Claude Code — no API key or token needed.
    Unsets CLAUDECODE so this works when called from inside Claude Code
    (e.g. lex_server.py MCP tool).
    """
    import os
    os.environ.pop("CLAUDECODE", None)
    return asyncio.run(_agent_sdk_complete(prompt))


# ── Template Loader ─────────────────────────────────────────

def _load_prompt(name: str, **kwargs) -> str:
    """Load a prompt template from prompts/ and substitute placeholders."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    template = path.read_text(encoding="utf-8")
    for key, value in kwargs.items():
        template = template.replace("{{" + key.upper() + "}}", str(value))
    return template


# ── Stage 1: Translate + Categorize ─────────────────────────

def _stage1(
    articles: List[Dict],
    batch_size: int = 50,
) -> List[Dict]:
    """Stage 1: Translate, categorize (13 categories), score relevance.

    Processes in batches. Returns enriched article list.
    """
    enriched = []

    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(articles) + batch_size - 1) // batch_size
        log.info(f"Stage 1 batch {batch_num}/{total_batches}: {len(batch)} articles")

        items_text = "\n".join([
            f"[{j}] SOURCE: {a.get('source', '?')} | TITLE: {a.get('title', a.get('subject', ''))[:200]} | SUMMARY: {a.get('content', a.get('body', ''))[:300]}"
            for j, a in enumerate(batch)
        ])

        prompt = _load_prompt("stage1", ARTICLES=items_text)

        try:
            response_text = _retry_with_backoff(_llm_complete, prompt, 4096)
            parsed = _parse_claude_json(response_text)
            if parsed and isinstance(parsed, list):
                for item in parsed:
                    idx = item.get("index", -1)
                    if 0 <= idx < len(batch):
                        article = batch[idx].copy()
                        article["english_title"] = item.get("english_title", article.get("title", ""))
                        article["category"] = item.get("category", "other")
                        article["relevance"] = item.get("relevance", 1)
                        enriched.append(article)
            else:
                log.warning(f"Stage 1 batch {batch_num} JSON parse failed, passing through raw")
                for a in batch:
                    a["english_title"] = a.get("title", "")
                    a["category"] = "other"
                    a["relevance"] = 3
                    enriched.append(a)

        except Exception as e:
            log.error(f"Stage 1 batch {batch_num} failed: {e}")
            for a in batch:
                a["english_title"] = a.get("title", "")
                a["category"] = "other"
                a["relevance"] = 3
                enriched.append(a)

    return enriched


# ── Stage 2: Pattern Analysis + Briefing ────────────────────

def _stage2(
    articles: List[Dict],
    historical_context: str = "",
) -> Dict:
    """Stage 2: Cross-source pattern analysis with historical context.

    Returns {"briefing": "...", "drafts": [...]}.
    """
    if not articles:
        return {"briefing": "", "drafts": []}

    # Group by category for structured input
    by_category = {}  # type: Dict[str, List[Dict]]
    for a in articles:
        cat = a.get("category", "other")
        by_category.setdefault(cat, []).append(a)

    sections = []
    for cat, items in sorted(by_category.items()):
        lines = [f"\n## {cat.upper()} ({len(items)} articles)"]
        for a in items:
            src = a.get("source", "?")
            title = a.get("english_title", a.get("title", ""))
            rel = a.get("relevance", "?")
            summary = a.get("content", a.get("body", ""))[:200]
            lines.append(f"- [{src}] (relevance:{rel}) {title}")
            if summary:
                lines.append(f"  Summary: {summary}")
        sections.append("\n".join(lines))

    categorized_text = "\n".join(sections)

    prompt = _load_prompt(
        "stage2",
        ARTICLES=categorized_text,
        HISTORICAL_CONTEXT=historical_context or "",
    )

    try:
        response_text = _retry_with_backoff(_llm_complete, prompt, 8192)
        parsed = _parse_claude_json(response_text)
        if parsed and isinstance(parsed, dict):
            return {
                "briefing": parsed.get("briefing", ""),
                "drafts": parsed.get("drafts", []),
            }
    except Exception as e:
        log.error(f"Stage 2 failed: {e}")

    return {"briefing": "", "drafts": []}


def _extract_lead(briefing_text: str) -> Optional[str]:
    """Extract the LEAD paragraph from a briefing for use as fallback_body."""
    if not briefing_text:
        return None
    for section in briefing_text.split("\n\n"):
        section = section.strip()
        if section and not section.startswith("#"):
            return section[:500]
    return briefing_text[:500]


# ── Main Entry Point ────────────────────────────────────────

def run_analyze() -> Dict:
    """Full analyze cycle: read pending articles -> enrich -> briefing -> queue posts.

    Returns summary dict.
    """
    run_id = start_scrape_run(mode="analyze")
    log.info(f"Analyze run {run_id} started")

    articles = get_pending_articles(limit=500)
    if not articles:
        log.info("No pending articles to analyze")
        finish_scrape_run(run_id, 0, 0, [], [])
        return {"run_id": run_id, "analyzed": 0, "briefing": False}

    log.info(f"Analyzing {len(articles)} pending articles")

    # Convert Supabase rows to working format (each carries its own UUID)
    working = []
    all_ids = {a["id"] for a in articles}
    for a in articles:
        working.append({
            "source": a["source"],
            "title": a["title"],
            "subject": a["title"],
            "body": a.get("body") or "",
            "content": a.get("body") or "",
            "date": a.get("published_at") or a["scraped_at"],
            "url": a.get("url") or "",
            "id": a["id"],
        })

    # Stage 1: Translate, categorize, score
    log.info("Stage 1: Translating and categorizing...")
    enriched = _stage1(working)
    log.info(f"Stage 1 complete: {len(enriched)} enriched")

    # Write enrichment back to Supabase using each article's own ID
    enriched_ids = set()
    for e in enriched:
        article_id = e.get("id")
        if not article_id:
            continue
        enriched_ids.add(article_id)
        update_article_enrichment(
            article_id,
            english_title=e.get("english_title", ""),
            category=e.get("category", "other"),
            relevance=e.get("relevance", 1),
        )

    # Mark articles dropped by Stage 1 as failed (not silently "analyzed")
    dropped_ids = list(all_ids - enriched_ids)
    if dropped_ids:
        log.warning(f"Stage 1 dropped {len(dropped_ids)} articles — marking as enrichment_failed")
        mark_articles_status(dropped_ids, "enrichment_failed")

    # Upsert enriched articles to Pinecone (with enrichment data)
    for e in enriched:
        e["article_id"] = e.get("id", "")
        e["published_at"] = e.get("date", "")
    upsert_articles(enriched)

    # Filter to relevance >= 3
    relevant = [e for e in enriched if e.get("relevance", 1) >= 3]
    log.info(f"Relevance filter: {len(enriched)} -> {len(relevant)} (score >= 3)")

    briefing_text = ""
    drafts = []

    if relevant:
        # Fetch historical context from Pinecone
        historical = get_historical_context(relevant, days=30)
        if historical:
            log.info(f"Historical context: {len(historical)} chars")

        # Stage 2: Pattern analysis + briefing generation
        log.info("Stage 2: Pattern analysis and briefing generation...")
        result = _stage2(relevant, historical_context=historical)
        briefing_text = result.get("briefing", "")
        drafts = result.get("drafts", [])
        log.info(f"Stage 2 complete: {len(briefing_text)} char briefing, {len(drafts)} drafts")

    # Insert briefing into Supabase
    briefing_id = None
    if briefing_text:
        briefing_id = insert_briefing(
            briefing_text=briefing_text,
            article_count=len(relevant),
            model_used="agent-sdk",
            scrape_run_id=run_id,
        )
        log.info(f"Briefing {briefing_id} saved")

        # Email delivery (graceful degradation)
        try:
            from lib.email import send_briefing
            send_briefing(briefing_text, briefing_id)
        except ImportError:
            log.debug("Email module not available, skipping email delivery")
        except Exception as e:
            log.warning(f"Email delivery failed: {e}")

    # Queue posts for publishing
    lead_text = _extract_lead(briefing_text)
    posts_queued = 0

    for draft in drafts:
        urgency = draft.get("urgency", "medium")

        global_post = draft.get("global_post") or draft.get("global_draft") or {}
        if global_post.get("text"):
            for platform in ["linkedin", "devto", "hashnode", "blogger"]:
                title = draft.get("english_title") or draft.get("summary") or ""
                enqueue_post(
                    platform=platform,
                    body=global_post["text"],
                    title=title if platform in ("devto", "hashnode", "blogger") else None,
                    urgency=urgency,
                    language="en",
                    fallback_body=lead_text,
                    briefing_id=briefing_id,
                )
                posts_queued += 1

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

    # Mark only successfully enriched articles as analyzed (dropped ones
    # were already marked "enrichment_failed" above)
    if enriched_ids:
        mark_articles_status(list(enriched_ids), "analyzed")

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
