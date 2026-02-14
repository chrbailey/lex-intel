"""
Lex Supabase client — thin wrapper over supabase-py.

Replaces Ahgen's JSON file I/O (state.json, pending.json) with Supabase tables.
All methods are synchronous (supabase-py uses httpx under the hood).
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from supabase import create_client, Client


def _get_client() -> Client:
    """Create Supabase client from environment variables."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)


def _normalize_title(title: str) -> str:
    """Normalize a title for dedup comparison. Matches Ahgen's logic."""
    title = unicodedata.normalize("NFKC", title).lower()
    title = re.sub(r'[^\w\s]', '', title)
    return re.sub(r'\s+', ' ', title).strip()


def _source_id(source: str, title: str, url: Optional[str] = None) -> str:
    """Generate a deterministic source_id from source + title/url."""
    key = f"{source}:{url or title}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ── Scrape Runs ──────────────────────────────────────────────

def start_scrape_run(mode: str = "scrape") -> str:
    """Create a new scrape_run, return its ID."""
    client = _get_client()
    result = client.table("scrape_runs").insert({
        "mode": mode,
    }).execute()
    return result.data[0]["id"]


def finish_scrape_run(
    run_id: str,
    articles_found: int,
    articles_new: int,
    sources_ok: List[str],
    sources_failed: List[str],
    error: Optional[str] = None,
) -> None:
    """Mark a scrape_run as finished with stats."""
    client = _get_client()
    started = client.table("scrape_runs").select("started_at").eq("id", run_id).execute()
    started_at = datetime.fromisoformat(started.data[0]["started_at"])
    duration = (datetime.now(timezone.utc) - started_at).total_seconds()

    client.table("scrape_runs").update({
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": round(duration, 1),
        "articles_found": articles_found,
        "articles_new": articles_new,
        "sources_ok": sources_ok,
        "sources_failed": sources_failed,
        "error": error,
    }).eq("id", run_id).execute()


# ── Dedup ────────────────────────────────────────────────────

def is_duplicate(title: str, threshold: float = 0.65) -> bool:
    """Check if a normalized title is a near-duplicate of recent titles.

    Uses Postgres trigram similarity (pg_trgm) if available, otherwise
    falls back to exact match on title_norm. For the MVP, we do exact
    match + a 30-day window. Fuzzy matching can be added via pg_trgm extension.
    """
    norm = _normalize_title(title)
    if not norm:
        return True  # empty title = skip

    client = _get_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    # Exact match check (fast, covers most cases)
    result = client.table("dedup_titles") \
        .select("id") \
        .eq("title_norm", norm) \
        .gte("seen_at", cutoff) \
        .limit(1) \
        .execute()

    return len(result.data) > 0


def record_title(title: str, source: str) -> None:
    """Record a title in the dedup window."""
    norm = _normalize_title(title)
    if not norm:
        return

    client = _get_client()
    client.table("dedup_titles").insert({
        "title_norm": norm,
        "source": source,
    }).execute()


def cleanup_dedup(days: int = 30) -> int:
    """Remove dedup titles older than N days. Returns count removed."""
    client = _get_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = client.table("dedup_titles") \
        .delete() \
        .lt("seen_at", cutoff) \
        .execute()
    return len(result.data)


# ── Articles ─────────────────────────────────────────────────

def insert_articles(articles: List[Dict], scrape_run_id: str) -> int:
    """Insert deduplicated articles into Supabase. Returns count inserted."""
    if not articles:
        return 0

    client = _get_client()
    rows = []

    for a in articles:
        title = a.get("title") or a.get("subject") or ""
        if not title:
            continue

        norm = _normalize_title(title)
        source = a.get("source", "unknown")

        rows.append({
            "source": source,
            "source_id": a.get("id") or _source_id(source, title, a.get("url")),
            "title": title[:1000],
            "title_norm": norm,
            "url": a.get("url"),
            "body": (a.get("body") or a.get("content") or "")[:10000],
            "published_at": a.get("date") or a.get("published"),
            "scrape_run_id": scrape_run_id,
            "status": "pending",
        })

    if not rows:
        return 0

    # Insert in batches of 100
    inserted = 0
    for i in range(0, len(rows), 100):
        batch = rows[i:i + 100]
        result = client.table("articles").insert(batch).execute()
        inserted += len(result.data)

    return inserted


def get_pending_articles(limit: int = 500) -> List[Dict]:
    """Fetch articles with status='pending', ordered by scraped_at."""
    client = _get_client()
    result = client.table("articles") \
        .select("*") \
        .eq("status", "pending") \
        .order("scraped_at", desc=False) \
        .limit(limit) \
        .execute()
    return result.data


def update_article_enrichment(article_id: str, english_title: str, category: str, relevance: int) -> None:
    """Update an article with Stage 1 enrichment data."""
    client = _get_client()
    client.table("articles").update({
        "english_title": english_title,
        "category": category,
        "relevance": relevance,
        "status": "analyzed",
    }).eq("id", article_id).execute()


def mark_articles_status(article_ids: List[str], status: str) -> None:
    """Bulk update article status."""
    if not article_ids:
        return
    client = _get_client()
    client.table("articles").update({
        "status": status,
    }).in_("id", article_ids).execute()


# ── Briefings ────────────────────────────────────────────────

def insert_briefing(
    briefing_text: str,
    article_count: int,
    model_used: str = "claude-sonnet-4-20250514",
    scrape_run_id: Optional[str] = None,
) -> str:
    """Insert a briefing, return its ID."""
    client = _get_client()
    result = client.table("briefings").insert({
        "briefing_text": briefing_text,
        "article_count": article_count,
        "model_used": model_used,
        "scrape_run_id": scrape_run_id,
    }).execute()
    return result.data[0]["id"]


def mark_briefing_emailed(briefing_id: str) -> None:
    """Mark a briefing as emailed."""
    client = _get_client()
    client.table("briefings").update({
        "email_sent": True,
        "email_sent_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", briefing_id).execute()


# ── Publish Queue ────────────────────────────────────────────

def enqueue_post(
    platform: str,
    body: str,
    title: Optional[str] = None,
    urgency: str = "medium",
    language: str = "en",
    fallback_body: Optional[str] = None,
    briefing_id: Optional[str] = None,
    article_id: Optional[str] = None,
) -> str:
    """Add a post to the publish queue. Returns queue item ID."""
    priority_map = {"high": 1, "medium": 2, "low": 3}

    client = _get_client()
    result = client.table("publish_queue").insert({
        "platform": platform,
        "title": title,
        "body": body,
        "urgency": urgency,
        "language": language,
        "priority": priority_map.get(urgency, 2),
        "fallback_body": fallback_body,
        "briefing_id": briefing_id,
        "article_id": article_id,
    }).execute()
    return result.data[0]["id"]


def get_publishable(platform: Optional[str] = None, limit: int = 20) -> List[Dict]:
    """Get items ready to publish, ordered by priority then age.

    Includes both 'queued' items and 'retry_queued' items whose
    next_retry_at has passed.
    """
    client = _get_client()
    now = datetime.now(timezone.utc).isoformat()

    # Get queued items
    query = client.table("publish_queue") \
        .select("*") \
        .eq("status", "queued") \
        .order("priority") \
        .order("created_at") \
        .limit(limit)

    if platform:
        query = query.eq("platform", platform)

    queued = query.execute().data

    # Get retry items whose time has come
    retry_query = client.table("publish_queue") \
        .select("*") \
        .eq("status", "retry_queued") \
        .lte("next_retry_at", now) \
        .order("priority") \
        .order("next_retry_at") \
        .limit(limit)

    if platform:
        retry_query = retry_query.eq("platform", platform)

    retries = retry_query.execute().data

    return retries + queued  # retries first (they've been waiting)


def mark_published(queue_id: str, platform_id: str) -> None:
    """Mark a queue item as successfully published."""
    client = _get_client()
    now = datetime.now(timezone.utc).isoformat()

    # Append to publish_log
    item = client.table("publish_queue").select("publish_log").eq("id", queue_id).execute()
    log = item.data[0]["publish_log"] if item.data else []
    log.append({"at": now, "status": "published", "platform_id": platform_id})

    client.table("publish_queue").update({
        "status": "published",
        "published_at": now,
        "platform_id": platform_id,
        "publish_log": log,
        "error": None,
    }).eq("id", queue_id).execute()


def mark_publish_failed(queue_id: str, error: str) -> None:
    """Mark a queue item as failed. Schedules retry if under max_retries."""
    client = _get_client()
    now = datetime.now(timezone.utc).isoformat()

    item = client.table("publish_queue") \
        .select("retry_count, max_retries, publish_log") \
        .eq("id", queue_id).execute()

    if not item.data:
        return

    row = item.data[0]
    log = row["publish_log"] or []
    log.append({"at": now, "status": "failed", "error": error})
    new_count = row["retry_count"] + 1

    if new_count < row["max_retries"]:
        # Exponential backoff: 5min, 20min, 80min
        backoff_minutes = 5 * (4 ** row["retry_count"])
        next_retry = (datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)).isoformat()

        client.table("publish_queue").update({
            "status": "retry_queued",
            "retry_count": new_count,
            "next_retry_at": next_retry,
            "publish_log": log,
            "error": error,
        }).eq("id", queue_id).execute()
    else:
        # Exhausted retries
        client.table("publish_queue").update({
            "status": "failed",
            "retry_count": new_count,
            "publish_log": log,
            "error": f"Exhausted {row['max_retries']} retries. Last: {error}",
        }).eq("id", queue_id).execute()
