"""
Lex scrape module — wraps Ahgen's scrapers with Supabase persistence.

Imports Ahgen's fetch functions directly (via sys.path), deduplicates
against the dedup_titles table, and inserts new articles into Supabase.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple

# Add Ahgen to path so we can import its scrapers
AHGEN_DIR = Path(os.environ.get("AHGEN_DIR", Path.home() / "ahgen"))
if str(AHGEN_DIR) not in sys.path:
    sys.path.insert(0, str(AHGEN_DIR))

from lib.db import (
    start_scrape_run,
    finish_scrape_run,
    is_duplicate,
    record_title,
    insert_articles,
)
from lib.vectors import find_semantic_duplicates, upsert_articles

log = logging.getLogger("lex.scrape")


def _fetch_china_sources() -> Tuple[List[Dict], List[str], List[str]]:
    """Run all Ahgen scrapers, return (articles, ok_sources, failed_sources)."""
    from scrapers import (
        fetch_36kr, fetch_huxiu, fetch_infoq_china, fetch_csdn,
        fetch_sap_china, fetch_kingdee, fetch_yonyou,
        fetch_leiphone, fetch_caixin, fetch_jiemian, fetch_zhidx,
    )

    scrapers = [
        ("36kr", fetch_36kr),
        ("huxiu", fetch_huxiu),
        ("infoq_china", fetch_infoq_china),
        ("csdn", fetch_csdn),
        ("sap_china", fetch_sap_china),
        ("kingdee", fetch_kingdee),
        ("yonyou", fetch_yonyou),
        ("leiphone", fetch_leiphone),
        ("caixin", fetch_caixin),
        ("jiemian", fetch_jiemian),
        ("zhidx", fetch_zhidx),
    ]

    all_articles = []
    ok = []
    failed = []

    for name, func in scrapers:
        try:
            articles = func()
            # Normalize to common format
            for a in articles:
                a.setdefault("source", name)
                a.setdefault("title", a.get("subject", ""))
                a.setdefault("body", a.get("content", ""))
            all_articles.extend(articles)
            ok.append(name)
            log.info(f"[{name}] {len(articles)} articles")
        except Exception as e:
            log.warning(f"[{name}] failed: {e}")
            failed.append(name)

    return all_articles, ok, failed


def _fetch_newsletters() -> Tuple[List[Dict], bool]:
    """Fetch Gmail newsletters using Ahgen's Gmail integration.

    Returns (articles, success). Does not fail the whole run if Gmail is down.
    """
    try:
        from ahgen import fetch_newsletters, load_json, CONFIG_PATH, STATE_PATH
        config = load_json(CONFIG_PATH)
        state = load_json(STATE_PATH, default={"processed_newsletter_ids": []})

        newsletters = fetch_newsletters(config, state)
        log.info(f"[gmail] {len(newsletters)} newsletters")
        return newsletters, True
    except Exception as e:
        log.warning(f"[gmail] failed: {e}")
        return [], False


def deduplicate(articles: List[Dict]) -> List[Dict]:
    """Filter out articles via exact title dedup + semantic similarity check."""
    unique = []
    semantic_dupes = 0
    for a in articles:
        title = a.get("title") or a.get("subject") or ""
        if not title:
            continue
        # Exact title dedup (Supabase dedup_titles table)
        if is_duplicate(title):
            continue
        # Semantic dedup (Pinecone — catches paraphrased duplicates)
        body = a.get("body") or a.get("content") or ""
        matches = find_semantic_duplicates(title, body, threshold=0.85)
        if matches:
            semantic_dupes += 1
            log.debug(f"Semantic dupe: '{title[:60]}' ~ '{matches[0]['english_title'][:60]}' (score={matches[0]['score']:.2f})")
            continue
        unique.append(a)
        record_title(title, a.get("source", "unknown"))

    removed = len(articles) - len(unique)
    if removed > 0:
        log.info(f"Dedup: {len(articles)} -> {len(unique)} ({removed} duplicates, {semantic_dupes} semantic)")

    return unique


def run_scrape() -> Dict:
    """Full scrape cycle: fetch all sources → dedup → insert to Supabase.

    Returns summary dict with counts and run_id.
    """
    run_id = start_scrape_run(mode="scrape")
    log.info(f"Scrape run {run_id} started")

    # Fetch from all sources
    china_articles, ok_sources, failed_sources = _fetch_china_sources()
    newsletters, gmail_ok = _fetch_newsletters()

    if gmail_ok:
        ok_sources.append("gmail")
    else:
        failed_sources.append("gmail")

    all_articles = china_articles + newsletters
    total_found = len(all_articles)

    if not all_articles:
        log.info("No articles found across any source")
        finish_scrape_run(run_id, 0, 0, ok_sources, failed_sources)
        return {"run_id": run_id, "found": 0, "new": 0}

    # Deduplicate against Supabase dedup_titles
    unique = deduplicate(all_articles)

    # Insert into articles table
    inserted = insert_articles(unique, run_id)

    # Upsert raw articles to Pinecone (pre-enrichment, will be re-upserted after Stage 1)
    upsert_articles(unique)

    # Finish run
    finish_scrape_run(
        run_id,
        articles_found=total_found,
        articles_new=inserted,
        sources_ok=ok_sources,
        sources_failed=failed_sources,
    )

    log.info(f"Scrape complete: {total_found} found, {inserted} new, {len(failed_sources)} sources failed")

    return {
        "run_id": run_id,
        "found": total_found,
        "new": inserted,
        "sources_ok": ok_sources,
        "sources_failed": failed_sources,
    }
