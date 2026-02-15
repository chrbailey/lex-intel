"""
Lex pgvector layer — semantic search, dedup, and multi-agent vector ops.

Replaces the old Pinecone implementation (v1) with Supabase pgvector.
Embeddings are generated via Voyage AI (voyage-3-lite, 1536 dimensions)
and stored directly in Postgres VECTOR(1536) columns. Similarity search
uses cosine distance (<=>)  via server-side SQL functions (match_articles,
match_research_items) called through Supabase RPC.

All operations degrade gracefully: if voyageai is unavailable or the
embedding call fails, functions return empty results rather than raising.

Public API (backward-compatible):
    upsert_articles(articles)                    -> int
    find_semantic_duplicates(title, body, thr)   -> List[Dict]
    get_historical_context(today, days, top_k)   -> str
    search(query, top_k)                         -> List[Dict]

New helpers for multi-agent pipeline:
    embed_text(text)                             -> list[float]
    vector_search(query, table, limit, ...)      -> List[Dict]
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger("lex.vectors")

# ── Embedding config ────────────────────────────────────────
VOYAGE_MODEL = "voyage-3-lite"   # 1536 dimensions, recommended by Supabase
EMBEDDING_DIM = 1536
BATCH_SIZE = 50                  # max articles per embedding batch

# Lazy-loaded Voyage AI client (None = not yet initialised, False = unavailable)
_vo_client: Any = None


def _get_voyage_client():
    """Lazy-init the Voyage AI client. Returns None if unavailable."""
    global _vo_client
    if _vo_client is False:
        return None
    if _vo_client is not None:
        return _vo_client

    api_key = os.environ.get("VOYAGE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("Neither VOYAGE_API_KEY nor ANTHROPIC_API_KEY set — embeddings disabled")
        _vo_client = False
        return None

    try:
        import voyageai
        _vo_client = voyageai.Client(api_key=api_key)
        return _vo_client
    except ImportError:
        log.warning("voyageai package not installed — embeddings disabled")
        _vo_client = False
        return None
    except Exception as e:
        log.warning("Voyage AI client init failed: %s", e)
        _vo_client = False
        return None


def _get_supabase():
    """Get the Supabase client via the shared db module."""
    from lib.db import _get_client
    return _get_client()


# ── Core helpers ────────────────────────────────────────────

def _article_id(source: str, title: str) -> str:
    """Deterministic content-hash ID for idempotent upserts.

    Kept for backward compatibility with the old Pinecone layer.
    """
    return hashlib.sha256(f"{source}:{title}".encode()).hexdigest()[:16]


def _make_content(english_title: str, body: str) -> str:
    """Build the text string that gets embedded."""
    return f"{english_title}\n\n{body[:2000]}"


# ── Embedding ───────────────────────────────────────────────

def embed_text(text: str) -> list[float]:
    """Generate an embedding vector for a single text string.

    Uses Voyage AI (voyage-3-lite, 1536 dims). Returns an empty list
    if the embedding cannot be generated for any reason.
    """
    if not text or not text.strip():
        return []

    vo = _get_voyage_client()
    if vo is None:
        return []

    try:
        # Voyage AI accepts a list of texts; we send one.
        result = vo.embed([text[:8000], ], model=VOYAGE_MODEL)
        if result and result.embeddings:
            return result.embeddings[0]
        return []
    except Exception as e:
        log.warning("embed_text failed: %s", e)
        return []


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns list of vectors (empty list on failure).

    Voyage AI supports batches of up to 128 texts. We cap at BATCH_SIZE.
    Failed items get an empty list so the caller can skip them.
    """
    vo = _get_voyage_client()
    if vo is None:
        return [[] for _ in texts]

    # Truncate each text to a reasonable size for the model context window
    truncated = [t[:8000] if t else "" for t in texts]

    try:
        result = vo.embed(truncated, model=VOYAGE_MODEL)
        if result and result.embeddings:
            return result.embeddings
        return [[] for _ in texts]
    except Exception as e:
        log.warning("Batch embedding failed: %s", e)
        return [[] for _ in texts]


# ── Public API (backward-compatible) ────────────────────────

def upsert_articles(articles: List[Dict]) -> int:
    """Embed and store vectors for a list of articles in Supabase.

    Each article dict should have: source, title, english_title, body,
    and optionally article_id / id (Supabase UUID).

    Returns the count of articles whose embeddings were successfully stored.
    """
    if not articles:
        return 0

    # Build texts for batch embedding
    texts: list[str] = []
    valid_articles: list[Dict] = []
    for a in articles:
        source = a.get("source", "unknown")
        title = a.get("title", "")
        english_title = a.get("english_title", title)
        body = a.get("body") or a.get("content") or ""
        content = _make_content(english_title, body)
        if not content.strip():
            continue
        texts.append(content)
        valid_articles.append(a)

    if not valid_articles:
        return 0

    # Embed in batches
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[i : i + BATCH_SIZE]
        batch_embeddings = _embed_batch(batch_texts)
        all_embeddings.extend(batch_embeddings)

    # Upsert embeddings into articles table
    client = _get_supabase()
    upserted = 0

    for a, embedding in zip(valid_articles, all_embeddings):
        if not embedding:
            continue

        article_id = a.get("article_id") or a.get("id")
        if not article_id:
            log.debug("Skipping article without id: %s", a.get("title", "?")[:60])
            continue

        try:
            client.table("articles").update({
                "embedding": embedding,
            }).eq("id", article_id).execute()
            upserted += 1
        except Exception as e:
            log.warning("Failed to store embedding for article %s: %s", article_id, e)

    log.info("Upserted %d/%d article embeddings to Supabase pgvector", upserted, len(valid_articles))
    return upserted


def find_semantic_duplicates(
    title: str,
    body: str = "",
    threshold: float = 0.85,
) -> List[Dict]:
    """Find semantically similar articles. Returns matches above threshold.

    Each match has: id, score, source, english_title.
    Uses cosine similarity via the match_articles RPC function.
    """
    query_text = _make_content(title, body)
    embedding = embed_text(query_text)
    if not embedding:
        return []

    try:
        client = _get_supabase()
        result = client.rpc("match_articles", {
            "query_embedding": embedding,
            "match_threshold": threshold,
            "match_count": 5,
        }).execute()

        matches = []
        for row in result.data or []:
            matches.append({
                "id": row.get("id", ""),
                "score": round(row.get("similarity", 0), 4),
                "source": row.get("source", ""),
                "english_title": row.get("english_title", ""),
            })
        return matches

    except Exception as e:
        log.warning("Semantic duplicate search failed: %s", e)
        return []


def get_historical_context(
    today_articles: List[Dict],
    days: int = 30,
    top_k: int = 10,
) -> str:
    """Retrieve past similar articles to inject as historical context for Stage 2.

    Builds a combined query from today's top articles and returns a formatted
    string of past related coverage, filtered to the last N days.
    """
    if not today_articles:
        return ""

    # Build a composite query from today's top titles
    top = sorted(today_articles, key=lambda a: a.get("relevance", 1), reverse=True)[:5]
    query_text = "\n".join(
        a.get("english_title", a.get("title", "")) for a in top
    )

    if not query_text.strip():
        return ""

    embedding = embed_text(query_text)
    if not embedding:
        return ""

    try:
        client = _get_supabase()
        result = client.rpc("match_articles", {
            "query_embedding": embedding,
            "match_threshold": 0.5,
            "match_count": top_k + len(today_articles),  # over-fetch to allow filtering
            "filter_days": days,
        }).execute()

        hits = result.data or []
        if not hits:
            return ""

        # Filter out today's articles (they may already have embeddings)
        today_ids = {
            _article_id(a.get("source", ""), a.get("title", ""))
            for a in today_articles
        }
        # Also filter by Supabase UUID if available
        today_uuids = {
            a.get("article_id") or a.get("id")
            for a in today_articles
            if a.get("article_id") or a.get("id")
        }

        lines = []
        for hit in hits:
            hit_id = hit.get("id", "")
            if hit_id in today_uuids:
                continue
            # Also check content-hash id
            hit_source = hit.get("source", "")
            hit_title = hit.get("english_title", "")
            if _article_id(hit_source, hit_title) in today_ids:
                continue

            category = hit.get("category", "")
            published = (hit.get("published_at") or "")[:10]
            if hit_title:
                lines.append(f"- [{hit_source}] ({published}, {category}) {hit_title}")

            if len(lines) >= top_k:
                break

        if not lines:
            return ""

        return "HISTORICAL CONTEXT (related past coverage):\n" + "\n".join(lines)

    except Exception as e:
        log.warning("Historical context retrieval failed: %s", e)
        return ""


def search(query: str, top_k: int = 10) -> List[Dict]:
    """Semantic search across the article corpus.

    Returns list of {id, score, source, english_title, category, relevance, published_at}.
    """
    embedding = embed_text(query)
    if not embedding:
        return []

    try:
        client = _get_supabase()
        result = client.rpc("match_articles", {
            "query_embedding": embedding,
            "match_threshold": 0.3,
            "match_count": top_k,
        }).execute()

        hits = []
        for row in result.data or []:
            hits.append({
                "id": row.get("id", ""),
                "score": round(row.get("similarity", 0), 4),
                "source": row.get("source", ""),
                "english_title": row.get("english_title", ""),
                "category": row.get("category", ""),
                "relevance": row.get("relevance", 0),
                "published_at": row.get("published_at", ""),
            })
        return hits

    except Exception as e:
        log.error("pgvector search failed: %s", e)
        return []


# ── Multi-agent helpers ─────────────────────────────────────

def vector_search(
    query_text: str,
    table: str = "articles",
    limit: int = 10,
    min_similarity: float = 0.5,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict]:
    """Generic vector similarity search across any embedding-enabled table.

    Supports the multi-agent MCP tools. Currently supports:
      - "articles"        (via match_articles RPC)
      - "research_items"  (via match_research_items RPC)

    Args:
        query_text:     The natural-language query to embed.
        table:          Target table name ("articles" or "research_items").
        limit:          Maximum number of results.
        min_similarity: Minimum cosine similarity threshold (0-1).
        filters:        Optional dict of extra filters:
                        - days (int): restrict to last N days
                        - category (str): filter by category (research_items only)

    Returns:
        List of dicts with table-specific columns plus a "similarity" score.
    """
    embedding = embed_text(query_text)
    if not embedding:
        return []

    filters = filters or {}

    rpc_map = {
        "articles": "match_articles",
        "research_items": "match_research_items",
    }

    rpc_name = rpc_map.get(table)
    if rpc_name is None:
        log.error("vector_search: unsupported table '%s' (supported: %s)", table, list(rpc_map.keys()))
        return []

    # Build RPC params
    params: Dict[str, Any] = {
        "query_embedding": embedding,
        "match_threshold": min_similarity,
        "match_count": limit,
    }

    # Optional time filter
    if "days" in filters and filters["days"] is not None:
        params["filter_days"] = int(filters["days"])

    # Category filter (research_items only)
    if table == "research_items" and "category" in filters and filters["category"]:
        params["filter_category"] = filters["category"]

    try:
        client = _get_supabase()
        result = client.rpc(rpc_name, params).execute()

        rows = []
        for row in result.data or []:
            row["similarity"] = round(row.get("similarity", 0), 4)
            rows.append(row)
        return rows

    except Exception as e:
        log.error("vector_search(%s) failed: %s", table, e)
        return []
