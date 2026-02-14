"""
Lex Pinecone vector layer — semantic search and dedup for articles.

Uses existing `claude-knowledge-base` index, `lex-articles` namespace.
Server-side inference (fieldMap.text = "content"), no local embedding needed.
All operations degrade gracefully if Pinecone is unavailable.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Dict, List, Optional, Tuple

from pinecone import Pinecone

log = logging.getLogger("lex.vectors")

INDEX_NAME = "claude-knowledge-base"
NAMESPACE = "lex-articles"
BATCH_SIZE = 50


def _get_index():
    """Get Pinecone index client. Returns None if unavailable."""
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        log.warning("PINECONE_API_KEY not set, vector operations disabled")
        return None
    try:
        pc = Pinecone(api_key=api_key)
        return pc.Index(INDEX_NAME)
    except Exception as e:
        log.warning(f"Pinecone connection failed: {e}")
        return None


def _article_id(source: str, title: str) -> str:
    """Deterministic content-hash ID for idempotent upserts."""
    return hashlib.sha256(f"{source}:{title}".encode()).hexdigest()[:16]


def _make_content(english_title: str, body: str) -> str:
    """Build the embedded content field."""
    return f"{english_title}\n\n{body[:2000]}"


def upsert_articles(articles: List[Dict]) -> int:
    """Batch upsert articles to Pinecone. Returns count upserted.

    Each article dict should have: source, title, english_title, body,
    category, relevance, published_at, and optionally article_id (Supabase UUID).
    """
    index = _get_index()
    if not index:
        return 0

    records = []
    for a in articles:
        source = a.get("source", "unknown")
        title = a.get("title", "")
        english_title = a.get("english_title", title)
        body = a.get("body") or a.get("content") or ""

        records.append({
            "_id": _article_id(source, title),
            "content": _make_content(english_title, body),
            "source": source,
            "category": a.get("category", "other"),
            "relevance": a.get("relevance", 1),
            "english_title": english_title[:500],
            "published_at": a.get("published_at") or "",
            "article_id": a.get("article_id") or a.get("id") or "",
        })

    upserted = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        try:
            index.upsert_records(NAMESPACE, batch)
            upserted += len(batch)
        except Exception as e:
            log.warning(f"Pinecone upsert batch {i // BATCH_SIZE + 1} failed: {e}")

    log.info(f"Upserted {upserted}/{len(records)} articles to Pinecone")
    return upserted


def find_semantic_duplicates(
    title: str,
    body: str = "",
    threshold: float = 0.85,
) -> List[Dict]:
    """Find semantically similar articles. Returns matches above threshold.

    Each match has: id, score, source, english_title.
    """
    index = _get_index()
    if not index:
        return []

    query_text = _make_content(title, body)
    try:
        results = index.search(
            namespace=NAMESPACE,
            query={"top_k": 5, "inputs": {"text": query_text}},
        )
        matches = []
        for hit in results.get("result", {}).get("hits", []):
            score = hit.get("_score", 0)
            if score >= threshold:
                fields = hit.get("fields", {})
                matches.append({
                    "id": hit.get("_id", ""),
                    "score": score,
                    "source": fields.get("source", ""),
                    "english_title": fields.get("english_title", ""),
                })
        return matches
    except Exception as e:
        log.warning(f"Semantic duplicate search failed: {e}")
        return []


def get_historical_context(
    today_articles: List[Dict],
    days: int = 30,
    top_k: int = 10,
) -> str:
    """Retrieve past similar articles to inject as historical context for Stage 2.

    Builds a combined query from today's top articles and returns a formatted
    string of past related coverage.
    """
    index = _get_index()
    if not index:
        return ""

    # Build a composite query from today's top titles
    top = sorted(today_articles, key=lambda a: a.get("relevance", 1), reverse=True)[:5]
    query_text = "\n".join(
        a.get("english_title", a.get("title", "")) for a in top
    )

    if not query_text.strip():
        return ""

    try:
        results = index.search(
            namespace=NAMESPACE,
            query={"top_k": top_k, "inputs": {"text": query_text}},
        )

        hits = results.get("result", {}).get("hits", [])
        if not hits:
            return ""

        # Filter out today's articles (they may already be in Pinecone)
        today_ids = {_article_id(a.get("source", ""), a.get("title", "")) for a in today_articles}

        lines = []
        for hit in hits:
            if hit.get("_id") in today_ids:
                continue
            fields = hit.get("fields", {})
            title = fields.get("english_title", "")
            source = fields.get("source", "")
            category = fields.get("category", "")
            date = fields.get("published_at", "")[:10]
            if title:
                lines.append(f"- [{source}] ({date}, {category}) {title}")

        if not lines:
            return ""

        return "HISTORICAL CONTEXT (related past coverage):\n" + "\n".join(lines)

    except Exception as e:
        log.warning(f"Historical context retrieval failed: {e}")
        return ""


def search(query: str, top_k: int = 10) -> List[Dict]:
    """Semantic search across the article corpus.

    Returns list of {id, score, source, english_title, category, published_at}.
    """
    index = _get_index()
    if not index:
        return []

    try:
        results = index.search(
            namespace=NAMESPACE,
            query={"top_k": top_k, "inputs": {"text": query}},
        )

        hits = []
        for hit in results.get("result", {}).get("hits", []):
            fields = hit.get("fields", {})
            hits.append({
                "id": hit.get("_id", ""),
                "score": round(hit.get("_score", 0), 4),
                "source": fields.get("source", ""),
                "english_title": fields.get("english_title", ""),
                "category": fields.get("category", ""),
                "relevance": fields.get("relevance", 0),
                "published_at": fields.get("published_at", ""),
            })
        return hits

    except Exception as e:
        log.error(f"Pinecone search failed: {e}")
        return []
