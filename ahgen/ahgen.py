#!/usr/bin/env python3
"""
Ahgen — Media Manager for ERP Access, Inc.

Mission: Deliver first-mover intelligence on ERP/tech breakthroughs.
Dual-track monitoring: English newsletters + Chinese-language sources.

Architecture: Single file, Karpathy-style. Prompts are the product.
"""

import difflib
import json
import logging
import logging.handlers
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List, Dict

import anthropic
import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# === Configuration ===

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"
PROMPTS_PATH = BASE_DIR / "prompts.md"
PENDING_PATH = BASE_DIR / "pending.json"
ENV_PATH = BASE_DIR / ".env"

# Load .env file if present (key=value format, no shell expansion)
_env_values = {}  # Keep raw .env values for fallback
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            _env_values[k] = v
            os.environ.setdefault(k, v)

# Fix for launchd: if env value is a literal "${VAR}" (unexpanded), use .env value
for k, v in os.environ.items():
    if v.startswith("${") and v.endswith("}") and k in _env_values:
        os.environ[k] = _env_values[k]

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# === Logging ===

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

log = logging.getLogger("ahgen")
log.setLevel(logging.INFO)

_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

# Rotating file handler: 5MB, 3 backups
_file_handler = logging.handlers.RotatingFileHandler(
    LOG_DIR / "ahgen.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(_log_fmt)
log.addHandler(_file_handler)

# Stdout for launchd capture
_stdout_handler = logging.StreamHandler(sys.stdout)
_stdout_handler.setFormatter(_log_fmt)
log.addHandler(_stdout_handler)


# === File I/O ===


def load_json(path: Path, default: Optional[Dict] = None) -> Dict:
    """Load JSON file with fallback to default."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default or {}


def save_json(path: Path, data: dict) -> None:
    """Save dict to JSON file with pretty formatting."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_prompts() -> str:
    """Load system prompt from prompts.md."""
    if PROMPTS_PATH.exists():
        return PROMPTS_PATH.read_text(encoding="utf-8")
    log.warning("prompts.md not found, using default prompt")
    return "You are Ahgen, a media manager for ERP Access, Inc."


# === Gmail Integration ===


def gmail_oauth_setup(config: dict) -> None:
    """One-time OAuth setup for Gmail. Saves tokens to config.json."""
    if "gmail_client_id" not in config or "gmail_client_secret" not in config:
        log.error("Missing gmail_client_id or gmail_client_secret in config.json")
        log.info("1. Go to https://console.cloud.google.com/apis/credentials")
        log.info("2. Create OAuth 2.0 Client ID (Desktop app)")
        log.info("3. Add client_id and client_secret to config.json")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": config["gmail_client_id"],
            "client_secret": config["gmail_client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, GMAIL_SCOPES)
    creds = flow.run_local_server(port=0)

    # Save tokens to config
    config["gmail_token"] = creds.token
    config["gmail_refresh_token"] = creds.refresh_token
    config["gmail_token_expiry"] = creds.expiry.isoformat() if creds.expiry else None
    save_json(CONFIG_PATH, config)
    log.info("Gmail OAuth tokens saved to config.json")


def get_gmail_credentials(config: Dict) -> Optional[Credentials]:
    """Get valid Gmail credentials, refreshing if needed."""
    if "gmail_token" not in config:
        return None

    # Parse expiry so creds.expired works correctly
    expiry = None
    expiry_str = config.get("gmail_token_expiry")
    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str)
        except (ValueError, TypeError):
            pass

    creds = Credentials(
        token=config.get("gmail_token"),
        refresh_token=config.get("gmail_refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.get("gmail_client_id"),
        client_secret=config.get("gmail_client_secret"),
        expiry=expiry,
    )

    if (creds.expired or not creds.valid) and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Update stored token
            config["gmail_token"] = creds.token
            config["gmail_token_expiry"] = creds.expiry.isoformat() if creds.expiry else None
            save_json(CONFIG_PATH, config)
            log.info("Gmail token refreshed")
        except Exception as e:
            log.error(f"Failed to refresh Gmail token: {e}")
            return None

    return creds


def fetch_newsletters(config: dict, state: dict) -> List[Dict]:
    """Fetch unread newsletters from Gmail inbox."""
    creds = get_gmail_credentials(config)
    if not creds:
        log.warning("No Gmail credentials, skipping newsletter fetch")
        return []

    newsletters = []
    try:
        service = build("gmail", "v1", credentials=creds)

        # Get unread messages from inbox
        query = "is:unread in:inbox"
        last_processed = state.get("last_newsletter_id")

        results = service.users().messages().list(
            userId="me", q=query, maxResults=10
        ).execute()

        messages = results.get("messages", [])
        log.info(f"Found {len(messages)} unread emails")

        for msg_info in messages:
            msg_id = msg_info["id"]

            # Skip if already processed
            if msg_id == last_processed:
                break
            if msg_id in state.get("processed_newsletter_ids", []):
                continue

            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()

            # Extract headers
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

            # Extract body (simplified - handles text/plain)
            body = ""
            payload = msg["payload"]
            if "body" in payload and payload["body"].get("data"):
                import base64
                body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
            elif "parts" in payload:
                for part in payload["parts"]:
                    if part["mimeType"] == "text/plain" and part["body"].get("data"):
                        import base64
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                        break

            newsletters.append({
                "id": msg_id,
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "body": body[:10000],  # Truncate to 10k chars
                "source": "gmail",
            })

    except HttpError as e:
        log.error(f"Gmail API error: {e}")
    except Exception as e:
        log.error(f"Failed to fetch newsletters: {e}")

    return newsletters


def send_briefing_email(config: dict, html_body: str, draft_count: int) -> bool:
    """Send HTML briefing digest via Gmail API."""
    creds = get_gmail_credentials(config)
    if not creds:
        log.error("No Gmail credentials for sending")
        return False

    to_address = config.get("draft_recipient", config.get("gmail_user", ""))
    if not to_address:
        log.error("No draft_recipient configured")
        return False

    try:
        service = build("gmail", "v1", credentials=creds)

        import base64
        from email.mime.text import MIMEText

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        subject = f"[Ahgen] Morning Briefing — {date_str} ({draft_count} items)"

        message = MIMEText(html_body, "html", "utf-8")
        message["to"] = to_address
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        log.info(f"Briefing email sent: {subject}")
        return True

    except Exception as e:
        log.error(f"Failed to send briefing email: {e}")
        return False


# === China Sources ===


def fetch_china_sources() -> List[Dict]:
    """Fetch content from Chinese sources via scrapers module.

    Sources (Tier 1):
    - 36Kr (RSS + scrape)
    - Huxiu (scrape)
    - InfoQ China (RSS)
    - CSDN (scrape)
    - SAP China News (scrape)
    - Kingdee/Yonyou IR pages (scrape)
    """
    try:
        from scrapers import fetch_all_china_sources

        results = fetch_all_china_sources()

        # Flatten results from all sources into single list
        all_items = []
        for source_name, articles in results.items():
            for article in articles:
                # Normalize to common format expected by analyze_and_generate_drafts
                all_items.append({
                    "source": article.get("source", source_name),
                    "title": article.get("title", ""),
                    "subject": article.get("title", ""),  # Alias for consistency
                    "body": article.get("content", ""),
                    "content": article.get("content", ""),
                    "date": article.get("published", ""),
                    "url": article.get("url", ""),
                })

        return all_items

    except ImportError:
        log.warning("scrapers module not found, skipping China sources")
        return []
    except Exception as e:
        log.error(f"Failed to fetch China sources: {e}")
        return []


# === Deduplication ===


def _normalize_title(title: str) -> str:
    """Normalize a title for comparison: lowercase, strip punctuation, collapse whitespace."""
    title = unicodedata.normalize("NFKC", title).lower()
    title = re.sub(r'[^\w\s]', '', title)
    return re.sub(r'\s+', ' ', title).strip()


def deduplicate_articles(articles: List[Dict], state: dict, threshold: float = 0.65) -> List[Dict]:
    """Remove near-duplicate articles within batch and against recent history.

    Uses difflib.SequenceMatcher on normalized titles. Keeps a rolling
    500-title window in state["recent_titles"].
    """
    recent_titles = state.get("recent_titles", [])
    seen = []  # Normalized titles in this batch
    unique = []

    for article in articles:
        raw_title = article.get("title", "") or article.get("subject", "")
        norm = _normalize_title(raw_title)
        if not norm:
            continue

        is_dupe = False

        # Check against this batch
        for prev in seen:
            if difflib.SequenceMatcher(None, norm, prev).ratio() >= threshold:
                is_dupe = True
                break

        # Check against recent history
        if not is_dupe:
            for prev in recent_titles:
                if difflib.SequenceMatcher(None, norm, prev).ratio() >= threshold:
                    is_dupe = True
                    break

        if not is_dupe:
            seen.append(norm)
            unique.append(article)

    # Update rolling window (keep last 500)
    recent_titles.extend(seen)
    state["recent_titles"] = recent_titles[-500:]

    removed = len(articles) - len(unique)
    if removed > 0:
        log.info(f"Dedup: {len(articles)} -> {len(unique)} ({removed} duplicates removed)")

    return unique


# === Claude Integration ===


def retry_with_backoff(func, *args, **kwargs) -> Any:
    """Retry a function with exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except (httpx.NetworkError, httpx.TimeoutException, anthropic.APIConnectionError) as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = RETRY_DELAY * (2 ** attempt)
            log.warning(f"Network error, retrying in {wait}s: {e}")
            time.sleep(wait)
    return None


def _parse_claude_json(response_text: str) -> Any:
    """Extract and parse JSON from Claude response, handling markdown wrapping."""
    # Handle markdown code blocks
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        parts = response_text.split("```")
        if len(parts) >= 2:
            response_text = parts[1]

    response_text = response_text.strip()
    # Remove trailing commas before ] or }
    response_text = re.sub(r',(\s*[}\]])', r'\1', response_text)

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # Try to extract just a JSON object
    match = re.search(r'\{[\s\S]*\}', response_text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    log.warning(f"Could not parse JSON. Response (first 1000 chars):\n{response_text[:1000]}")
    return None


def stage1_translate_categorize(
    client: anthropic.Anthropic,
    articles: List[Dict],
    batch_size: int = 50,
) -> List[Dict]:
    """Stage 1: Translate Chinese titles/summaries, categorize, score relevance.

    Processes in batches of batch_size. Returns enriched article list with
    english_title, category, and relevance_score fields added.
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

        prompt = f"""You are a China tech intelligence analyst. For each article below:
1. Translate the title to English (if already English, keep as-is)
2. Categorize: funding, m_and_a, product, regulation, breakthrough, personnel, market, other
3. Score relevance 1-5 for enterprise-tech/AI (5 = critical, 1 = irrelevant)

Return JSON array. Each element: {{"index": N, "english_title": "...", "category": "...", "relevance": N}}

ARTICLES:
{items_text}

Respond with valid JSON array only."""

        try:
            response = retry_with_backoff(
                client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            parsed = _parse_claude_json(response.content[0].text)
            if parsed and isinstance(parsed, list):
                for item in parsed:
                    idx = item.get("index", -1)
                    if 0 <= idx < len(batch):
                        article = batch[idx].copy()
                        article["english_title"] = item.get("english_title", article.get("title", ""))
                        article["category"] = item.get("category", "other")
                        article["relevance"] = item.get("relevance", 1)
                        enriched.append(article)
                    # Articles not in response are dropped (likely irrelevant)
            else:
                # Parsing failed — pass batch through unscored
                log.warning(f"Stage 1 batch {batch_num} JSON parse failed, passing through raw")
                for a in batch:
                    a["english_title"] = a.get("title", "")
                    a["category"] = "other"
                    a["relevance"] = 3
                    enriched.append(a)

        except Exception as e:
            log.error(f"Stage 1 batch {batch_num} failed: {e}")
            # Pass through on error
            for a in batch:
                a["english_title"] = a.get("title", "")
                a["category"] = "other"
                a["relevance"] = 3
                enriched.append(a)

    return enriched


def stage2_pattern_analysis(
    client: anthropic.Anthropic,
    system_prompt: str,
    articles: List[Dict],
) -> Dict:
    """Stage 2: Cross-source pattern analysis and morning briefing generation.

    Receives categorized, relevance-filtered articles.
    Returns {"briefing": "...", "drafts": [...]} dict.
    """
    if not articles:
        return {"briefing": "", "drafts": []}

    # Group by category for structured input
    by_category = {}
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

    prompt = f"""Analyze these categorized China tech articles and produce TWO outputs:

1. **MORNING BRIEFING** (300-500 words, Bloomberg style):
   Format: LEAD (biggest story) → PATTERNS (cross-source themes) → SIGNALS (emerging trends) → WATCHLIST (developing stories) → DATA (key numbers)

2. **POST DRAFTS** for the top 3-5 most notable items, each with dual China + Global posts.

Look for cross-source patterns — if multiple sources report the same theme, that's a signal.

CATEGORIZED ARTICLES:
{categorized_text}

Return JSON: {{"briefing": "markdown text...", "drafts": [{{same format as before}}]}}
Respond with valid JSON only."""

    try:
        response = retry_with_backoff(
            client.messages.create,
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        parsed = _parse_claude_json(response.content[0].text)
        if parsed and isinstance(parsed, dict):
            return {
                "briefing": parsed.get("briefing", ""),
                "drafts": parsed.get("drafts", []),
            }

        log.warning("Stage 2 JSON parse failed")
        return {"briefing": "", "drafts": []}

    except Exception as e:
        log.error(f"Stage 2 failed: {e}")
        return {"briefing": "", "drafts": []}


def analyze_and_generate_drafts(
    client: anthropic.Anthropic,
    system_prompt: str,
    content_items: List[Dict],
) -> List[Dict]:
    """Legacy single-stage fallback: analyze content and generate dual drafts."""
    if not content_items:
        return []

    content_text = "\n\n---\n\n".join([
        f"SOURCE: {item.get('source', 'unknown')}\n"
        f"TITLE/SUBJECT: {item.get('subject', item.get('title', 'N/A'))}\n"
        f"DATE: {item.get('date', 'N/A')}\n"
        f"CONTENT:\n{item.get('body', item.get('content', ''))[:5000]}"
        for item in content_items
    ])

    prompt = f"""Analyze the following content items and identify any notable ERP/tech breakthroughs or news.

For each notable item, generate dual drafts (China market + Global market) following the output format in your instructions.

If nothing is notable, respond with: {{"drafts": []}}

CONTENT ITEMS:
{content_text}

Respond with valid JSON only."""

    try:
        response = retry_with_backoff(
            client.messages.create,
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        parsed = _parse_claude_json(response.content[0].text)
        if parsed:
            return parsed.get("drafts", [])
        return []

    except Exception as e:
        log.error(f"Claude API error: {e}")
        return []


# === Main Loop ===


def run_cycle(config: dict, state: dict) -> dict:
    """Run one polling cycle: fetch, analyze, draft, send."""
    cycle_start = datetime.now(timezone.utc)
    log.info(f"=== Starting cycle at {cycle_start.isoformat()} ===")

    # Initialize Claude client
    api_key = os.environ.get("ANTHROPIC_API_KEY", config.get("anthropic_api_key"))
    if not api_key:
        log.error("No ANTHROPIC_API_KEY found in environment or config")
        return state

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = load_prompts()

    # Fetch content from all sources
    all_content = []

    # 1. Newsletters from Gmail
    newsletters = fetch_newsletters(config, state)
    all_content.extend(newsletters)
    log.info(f"Fetched {len(newsletters)} newsletters")

    # 2. China sources (placeholder for now)
    china_items = fetch_china_sources()
    all_content.extend(china_items)
    log.info(f"Fetched {len(china_items)} China source items")

    if not all_content:
        log.info("No new content to process")
        state["last_run"] = cycle_start.isoformat()
        state["last_run_items"] = 0
        return state

    # Deduplicate across sources and against recent history
    raw_count = len(all_content)
    all_content = deduplicate_articles(all_content, state)
    log.info(f"After dedup: {raw_count} raw -> {len(all_content)} unique")

    # Two-stage analysis pipeline
    from poster import save_briefing_to_disk, format_briefing_email

    briefing_text = ""
    drafts = []

    try:
        # Stage 1: Translate, categorize, score
        log.info("Stage 1: Translating and categorizing articles...")
        enriched = stage1_translate_categorize(client, all_content)
        log.info(f"Stage 1 complete: {len(enriched)} articles enriched")

        # Filter to relevance >= 3
        relevant = [a for a in enriched if a.get("relevance", 1) >= 3]
        log.info(f"Relevance filter: {len(enriched)} -> {len(relevant)} (score >= 3)")

        if relevant:
            # Stage 2: Pattern analysis + briefing
            log.info("Stage 2: Pattern analysis and briefing generation...")
            result = stage2_pattern_analysis(client, system_prompt, relevant)
            briefing_text = result.get("briefing", "")
            drafts = result.get("drafts", [])
            log.info(f"Stage 2 complete: briefing={len(briefing_text)} chars, {len(drafts)} drafts")

    except Exception as e:
        log.error(f"Two-stage pipeline failed: {e}, falling back to legacy")
        drafts = analyze_and_generate_drafts(client, system_prompt, all_content)

    log.info(f"Generated {len(drafts)} draft sets")

    # Save briefing to disk + send email digest
    save_briefing_to_disk(briefing_text, drafts)

    drafts_sent = 0
    if drafts or briefing_text:
        html_body = format_briefing_email(briefing_text, drafts)
        if send_briefing_email(config, html_body, len(drafts)):
            drafts_sent = len(drafts)
        else:
            log.warning("Email delivery failed, but markdown draft was saved")

    # Update state
    processed_ids = state.get("processed_newsletter_ids", [])
    for nl in newsletters:
        if nl["id"] not in processed_ids:
            processed_ids.append(nl["id"])

    # Keep only last 100 processed IDs
    state["processed_newsletter_ids"] = processed_ids[-100:]
    state["last_run"] = cycle_start.isoformat()
    state["last_run_items"] = len(all_content)
    state["last_run_drafts"] = len(drafts)
    state["last_run_sent"] = drafts_sent
    state["total_runs"] = state.get("total_runs", 0) + 1
    state["total_drafts"] = state.get("total_drafts", 0) + len(drafts)

    # Health tracking
    cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
    state["health"] = {
        "last_cycle_duration_s": round(cycle_duration, 1),
        "sources_attempted": len(china_items) > 0,
        "newsletter_count": len(newsletters),
        "china_article_count": len(china_items),
        "drafts_generated": len(drafts),
        "drafts_delivered": drafts_sent,
        "gmail_status": "ok" if newsletters is not None else "no_credentials",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    log.info(f"Cycle complete: {len(all_content)} items -> {len(drafts)} drafts -> {drafts_sent} sent ({cycle_duration:.1f}s)")
    return state


def run_scrape_only(config: dict, state: dict) -> dict:
    """Scrape-only mode: fetch, dedup, append to pending.json. No API calls."""
    cycle_start = datetime.now(timezone.utc)
    log.info(f"=== Scrape cycle at {cycle_start.isoformat()} ===")

    all_content = []

    # 1. Newsletters from Gmail
    newsletters = fetch_newsletters(config, state)
    all_content.extend(newsletters)
    log.info(f"Fetched {len(newsletters)} newsletters")

    # 2. China sources
    china_items = fetch_china_sources()
    all_content.extend(china_items)
    log.info(f"Fetched {len(china_items)} China source items")

    if not all_content:
        log.info("No new content found")
        state["last_scrape"] = cycle_start.isoformat()
        return state

    # Deduplicate
    raw_count = len(all_content)
    all_content = deduplicate_articles(all_content, state)
    log.info(f"After dedup: {raw_count} raw -> {len(all_content)} unique")

    # Append to pending.json (accumulate between analysis runs)
    pending = load_json(PENDING_PATH, default={"articles": [], "scraped_at": []})
    pending["articles"].extend(all_content)
    pending["scraped_at"].append(cycle_start.isoformat())
    # Cap at 500 articles to prevent unbounded growth
    pending["articles"] = pending["articles"][-500:]
    save_json(PENDING_PATH, pending)
    log.info(f"Pending: {len(pending['articles'])} articles waiting for analysis")

    # Update newsletter state
    processed_ids = state.get("processed_newsletter_ids", [])
    for nl in newsletters:
        if nl["id"] not in processed_ids:
            processed_ids.append(nl["id"])
    state["processed_newsletter_ids"] = processed_ids[-100:]
    state["last_scrape"] = cycle_start.isoformat()
    state["pending_count"] = len(pending["articles"])

    return state


def run_analyze_pending(config: dict, state: dict) -> dict:
    """Analyze pending articles and deliver briefing. Called after claude -p or via API."""
    cycle_start = datetime.now(timezone.utc)

    pending = load_json(PENDING_PATH, default={"articles": []})
    articles = pending.get("articles", [])

    if not articles:
        log.info("No pending articles to analyze")
        return state

    log.info(f"=== Analyzing {len(articles)} pending articles ===")

    # Check if analysis came via stdin (from claude -p)
    # If not, fall back to API
    analysis_result = None
    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                analysis_result = json.loads(stdin_data)
        except (json.JSONDecodeError, IOError):
            pass

    from poster import save_briefing_to_disk, format_briefing_email

    if analysis_result:
        # Analysis came from claude -p
        briefing_text = analysis_result.get("briefing", "")
        drafts = analysis_result.get("drafts", [])
        log.info(f"Received analysis from Claude Code: {len(briefing_text)} char briefing, {len(drafts)} drafts")
    else:
        # Fall back to API (legacy mode)
        api_key = os.environ.get("ANTHROPIC_API_KEY", config.get("anthropic_api_key"))
        if not api_key:
            log.error("No analysis input and no API key — cannot analyze")
            return state

        client = anthropic.Anthropic(api_key=api_key)
        system_prompt = load_prompts()

        try:
            enriched = stage1_translate_categorize(client, articles)
            relevant = [a for a in enriched if a.get("relevance", 1) >= 3]
            if relevant:
                result = stage2_pattern_analysis(client, system_prompt, relevant)
                briefing_text = result.get("briefing", "")
                drafts = result.get("drafts", [])
            else:
                briefing_text, drafts = "", []
        except Exception as e:
            log.error(f"API analysis failed: {e}")
            drafts = analyze_and_generate_drafts(client, system_prompt, articles)
            briefing_text = ""

    # Save and deliver
    save_briefing_to_disk(briefing_text, drafts)

    drafts_sent = 0
    if drafts or briefing_text:
        html_body = format_briefing_email(briefing_text, drafts)
        if send_briefing_email(config, html_body, len(drafts)):
            drafts_sent = len(drafts)
        else:
            log.warning("Email delivery failed, but markdown draft was saved")

    # Clear pending
    save_json(PENDING_PATH, {"articles": [], "scraped_at": []})
    log.info(f"Cleared pending queue after analysis")

    # Update state
    state["last_analysis"] = cycle_start.isoformat()
    state["last_run_items"] = len(articles)
    state["last_run_drafts"] = len(drafts)
    state["last_run_sent"] = drafts_sent
    state["total_runs"] = state.get("total_runs", 0) + 1
    state["total_drafts"] = state.get("total_drafts", 0) + len(drafts)
    state["pending_count"] = 0

    cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
    state["health"] = {
        "last_cycle_duration_s": round(cycle_duration, 1),
        "articles_analyzed": len(articles),
        "drafts_generated": len(drafts),
        "drafts_delivered": drafts_sent,
        "mode": "claude_code" if analysis_result else "api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    log.info(f"Analysis complete: {len(articles)} articles -> {len(drafts)} drafts -> {drafts_sent} sent ({cycle_duration:.1f}s)")
    return state


def dump_pending_for_claude() -> None:
    """Dump pending articles as structured prompt for claude -p. Outputs to stdout."""
    pending = load_json(PENDING_PATH, default={"articles": []})
    articles = pending.get("articles", [])

    if not articles:
        print('{"briefing": "", "drafts": []}')
        return

    system_prompt = load_prompts()

    # Build the prompt that claude -p will process
    items_text = "\n".join([
        f"[{i}] SOURCE: {a.get('source', '?')} | TITLE: {a.get('title', a.get('subject', ''))[:200]} | SUMMARY: {a.get('content', a.get('body', ''))[:300]}"
        for i, a in enumerate(articles)
    ])

    prompt = f"""You are Ahgen, a China tech intelligence agent for ERP Access, Inc.

{system_prompt}

## TASK

Analyze these {len(articles)} articles from Chinese tech sources. Produce:

1. **MORNING BRIEFING** (300-500 words, Bloomberg style):
   LEAD (biggest story) → PATTERNS (cross-source themes) → SIGNALS (emerging trends) → WATCHLIST (developing stories) → DATA (key numbers)

2. **POST DRAFTS** for the top 3-5 most notable items, each with:
   - summary, urgency (high/medium/low), source
   - global_post (English LinkedIn text)
   - china_post (Chinese text)

Return ONLY valid JSON: {{"briefing": "markdown...", "drafts": [...]}}

## ARTICLES

{items_text}"""

    print(prompt)


def main():
    """Main entry point.

    Modes:
      (no args)        — Legacy: full cycle with API calls
      --scrape-only    — Scrape + dedup + save to pending.json (free, runs every 15 min)
      --analyze        — Analyze pending articles (reads stdin from claude -p, or falls back to API)
      --dump-prompt    — Output structured prompt for piping to claude -p
      --setup-gmail    — One-time Gmail OAuth setup
    """
    mode = sys.argv[1] if len(sys.argv) > 1 else None

    # Load configuration
    config = load_json(CONFIG_PATH)
    if not config and mode != "--dump-prompt":
        log.error(f"No config.json found at {CONFIG_PATH}")
        sys.exit(1)

    if mode == "--setup-gmail":
        gmail_oauth_setup(config)
        return

    if mode == "--dump-prompt":
        dump_pending_for_claude()
        return

    # Load state
    state = load_json(STATE_PATH, default={
        "processed_newsletter_ids": [],
        "total_runs": 0,
        "total_drafts": 0,
    })

    try:
        if mode == "--scrape-only":
            log.info("Ahgen scrape-only mode")
            state = run_scrape_only(config, state)
        elif mode == "--analyze":
            log.info("Ahgen analyze mode")
            state = run_analyze_pending(config, state)
        else:
            # Legacy full cycle (API mode)
            log.info("Ahgen full cycle (legacy API mode)")
            state = run_cycle(config, state)

        save_json(STATE_PATH, state)

    except KeyboardInterrupt:
        log.info("Interrupted by user")
    except Exception as e:
        log.exception(f"Cycle failed: {e}")
        state["last_error"] = str(e)
        state["last_error_time"] = datetime.now(timezone.utc).isoformat()
        save_json(STATE_PATH, state)
        sys.exit(1)

    log.info("Ahgen cycle complete")


if __name__ == "__main__":
    main()
