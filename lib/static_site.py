"""
Lex static site generator — builds docs/ for GitHub Pages.

Generates:
  docs/index.html       — Latest briefing + recent articles (human + agent readable)
  docs/feed.json        — JSON feed of briefings (machine-readable, RFC 7159)
  docs/archive/YYYY-MM-DD.html — Daily briefing archive pages
  docs/llms.txt         — Agent discovery file (what this site offers)
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

log = logging.getLogger("lex.site")

DOCS_DIR = Path(__file__).parent.parent / "docs"
SITE_URL = "https://chrbailey.github.io/lex-intel"
SITE_TITLE = "Lex Intel — China AI Daily Briefing"
SITE_DESC = (
    "Daily intelligence briefings on Chinese AI developments. "
    "Scraped from 12 Chinese-language sources, analyzed by AI, "
    "published for humans and agents."
)


def _get_supabase():
    """Lazy Supabase client."""
    load_dotenv()
    from supabase import create_client

    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_ANON_KEY"],
    )


def _md_to_html(md: str) -> str:
    """Minimal markdown to HTML. Handles headers, bold, bullets, paragraphs."""
    lines = md.strip().split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # Close list if we're not in one
        if in_list and not stripped.startswith("- "):
            html_lines.append("</ul>")
            in_list = False

        if stripped.startswith("## "):
            html_lines.append(f'<h2>{_inline(stripped[3:])}</h2>')
        elif stripped.startswith("# "):
            html_lines.append(f'<h1>{_inline(stripped[2:])}</h1>')
        elif stripped.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_inline(stripped[2:])}</li>")
        elif stripped == "":
            continue
        else:
            html_lines.append(f"<p>{_inline(stripped)}</p>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def _inline(text: str) -> str:
    """Convert inline markdown (bold, italic) to HTML."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text


def _format_date(iso_str: str) -> str:
    """Parse ISO date string to human-readable format."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except (ValueError, AttributeError):
        return iso_str or "Unknown date"


def _date_slug(iso_str: str) -> str:
    """Extract YYYY-MM-DD from ISO string."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return "unknown"


# ── HTML Templates ──────────────────────────────────────────

STYLE = """
:root {
  --bg: #0d1117; --fg: #e6edf3; --accent: #58a6ff;
  --card-bg: #161b22; --border: #30363d; --muted: #8b949e;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  background: var(--bg); color: var(--fg); line-height: 1.6;
  max-width: 800px; margin: 0 auto; padding: 2rem 1rem;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
h2 { font-size: 1.3rem; margin: 1.5rem 0 0.5rem; color: var(--accent); }
p { margin-bottom: 0.8rem; }
ul { margin: 0.5rem 0 1rem 1.5rem; }
li { margin-bottom: 0.3rem; }
strong { color: #f0f6fc; }
.meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }
.card {
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem;
}
.article-list { list-style: none; padding: 0; margin: 0; }
.article-list li {
  padding: 0.6rem 0; border-bottom: 1px solid var(--border);
}
.article-list li:last-child { border-bottom: none; }
.source-tag {
  display: inline-block; font-size: 0.75rem; padding: 0.1rem 0.4rem;
  background: var(--border); border-radius: 3px; color: var(--muted);
  margin-right: 0.3rem;
}
.relevance { color: var(--accent); font-weight: 600; }
.nav { margin-bottom: 2rem; }
.nav a { margin-right: 1rem; }
footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.85rem; }
"""

def _page_html(title: str, body: str, nav: bool = True) -> str:
    """Wrap body content in full HTML page."""
    nav_html = ""
    if nav:
        nav_html = f"""<nav class="nav">
  <a href="{SITE_URL}/">Latest</a>
  <a href="{SITE_URL}/feed.json">JSON Feed</a>
  <a href="https://github.com/chrbailey/lex-intel">GitHub</a>
</nav>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <meta name="description" content="{SITE_DESC}">
  <meta name="robots" content="index, follow">
  <link rel="alternate" type="application/json" href="{SITE_URL}/feed.json" title="JSON Feed">
  <style>{STYLE}</style>
</head>
<body>
{nav_html}
{body}
<footer>
  <p>Generated by <a href="https://github.com/chrbailey/lex-intel">Lex Intel</a> — Chinese AI intelligence, daily.</p>
  <p>Sources: 36kr, Huxiu, InfoQ China, CSDN, SAP China, Kingdee, Yonyou, Leiphone, Caixin, Jiemian, Zhidx, Gmail newsletters</p>
  <p>Data: <a href="{SITE_URL}/feed.json">JSON Feed</a> &middot;
     Agent info: <a href="{SITE_URL}/llms.txt">llms.txt</a></p>
</footer>
</body>
</html>"""


# ── Generators ──────────────────────────────────────────────

def generate_site() -> Dict[str, Any]:
    """Generate the full static site from Supabase data."""
    sb = _get_supabase()
    stats = {"briefings": 0, "articles": 0, "pages": 0}

    # Fetch data
    briefings = (
        sb.table("briefings")
        .select("*")
        .order("created_at", desc=True)
        .limit(30)
        .execute()
        .data
    )

    articles = (
        sb.table("articles")
        .select("id,source,title,english_title,url,category,relevance,status,created_at")
        .eq("status", "analyzed")
        .order("created_at", desc=True)
        .limit(100)
        .execute()
        .data
    )

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "archive").mkdir(exist_ok=True)

    # 1. Generate index.html (latest briefing + recent articles)
    if briefings:
        latest = briefings[0]
        briefing_html = _md_to_html(latest["briefing_text"])
        date_str = _format_date(latest["created_at"])

        articles_html = _render_article_list(articles[:20])

        body = f"""
<h1>{SITE_TITLE}</h1>
<p class="meta">Latest briefing: {date_str} &middot; {latest['article_count']} articles analyzed &middot; Model: {latest.get('model_used', 'claude')}</p>

<div class="card">
{briefing_html}
</div>

<h2>Recent Articles ({len(articles[:20])})</h2>
{articles_html}

<h2>Archive</h2>
<ul>
"""
        for b in briefings[:10]:
            slug = _date_slug(b["created_at"])
            body += f'<li><a href="{SITE_URL}/archive/{slug}.html">{_format_date(b["created_at"])}</a> — {b["article_count"]} articles</li>\n'

        body += "</ul>"

        index_html = _page_html(SITE_TITLE, body)
        (DOCS_DIR / "index.html").write_text(index_html)
        stats["pages"] += 1
        log.info("Generated index.html")

    # 2. Generate archive pages
    for b in briefings:
        slug = _date_slug(b["created_at"])
        date_str = _format_date(b["created_at"])
        briefing_html = _md_to_html(b["briefing_text"])

        body = f"""
<h1>China AI Briefing — {date_str}</h1>
<p class="meta">{b['article_count']} articles analyzed &middot; Model: {b.get('model_used', 'claude')}</p>
<div class="card">
{briefing_html}
</div>
"""
        page = _page_html(f"China AI Briefing — {date_str}", body)
        (DOCS_DIR / "archive" / f"{slug}.html").write_text(page)
        stats["briefings"] += 1
        stats["pages"] += 1

    log.info(f"Generated {stats['briefings']} archive pages")

    # 3. Generate JSON Feed (RFC-style, agent-friendly)
    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": SITE_TITLE,
        "description": SITE_DESC,
        "home_page_url": SITE_URL,
        "feed_url": f"{SITE_URL}/feed.json",
        "language": "en",
        "items": [],
    }

    for b in briefings:
        slug = _date_slug(b["created_at"])
        feed["items"].append({
            "id": b["id"],
            "url": f"{SITE_URL}/archive/{slug}.html",
            "title": f"China AI Briefing — {_format_date(b['created_at'])}",
            "content_text": b["briefing_text"],
            "date_published": b["created_at"],
            "summary": b["briefing_text"][:300] + "...",
            "tags": ["china", "ai", "intelligence", "briefing"],
            "_lex": {
                "article_count": b["article_count"],
                "model_used": b.get("model_used"),
            },
        })

    (DOCS_DIR / "feed.json").write_text(
        json.dumps(feed, indent=2, default=str)
    )
    log.info("Generated feed.json")

    # 4. Generate llms.txt (agent discovery)
    llms_txt = f"""# {SITE_TITLE}

> Daily intelligence briefings on Chinese AI developments, scraped from 12 Chinese-language sources and analyzed by AI.

## What This Site Offers

- **Daily briefings** analyzing Chinese AI news across enterprise software, semiconductors, autonomous driving, regulation, and startups
- **Structured data** via JSON Feed at {SITE_URL}/feed.json
- **12 Chinese sources**: 36kr, Huxiu, InfoQ China, CSDN, SAP China, Kingdee, Yonyou, Leiphone, Caixin, Jiemian, Zhidx, Gmail newsletters
- **Analysis format**: LEAD / PATTERNS / SIGNALS / WATCHLIST / DATA sections

## For Agents

- JSON Feed: {SITE_URL}/feed.json (JSON Feed 1.1 format)
- Each feed item has `content_text` with the full briefing markdown
- Custom `_lex` field includes `article_count` and `model_used`
- Updated daily around 05:00 UTC

## Topics Covered

China AI policy, DeepSeek, Baidu, Alibaba Cloud, Tencent AI, Huawei Ascend, semiconductor supply chain, enterprise ERP (Yonyou, Kingdee, SAP China), autonomous driving (XPeng, BYD, Baidu Apollo), robotics, regulation (CAC, MIIT), venture funding, US-China tech competition

## Source Code

https://github.com/chrbailey/lex-intel
"""

    (DOCS_DIR / "llms.txt").write_text(llms_txt)
    log.info("Generated llms.txt")

    stats["articles"] = len(articles)
    return stats


def _render_article_list(articles: List[Dict]) -> str:
    """Render article list as HTML."""
    if not articles:
        return "<p>No articles yet.</p>"

    items = []
    for a in articles:
        title = a.get("english_title") or a.get("title", "Untitled")
        source = a.get("source", "unknown")
        relevance = a.get("relevance", 0)
        url = a.get("url", "#")
        rel_stars = "★" * min(relevance, 5) if relevance else ""

        items.append(
            f'<li><span class="source-tag">{source}</span>'
            f' <a href="{url}" target="_blank" rel="noopener">{title}</a>'
            f' <span class="relevance">{rel_stars}</span></li>'
        )

    return f'<ul class="article-list">{"".join(items)}</ul>'


# ── CLI Entry ────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    stats = generate_site()
    print(json.dumps(stats, indent=2))
