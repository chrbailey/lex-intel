"""
Beijing to Breakfast — PromptSpeak Governance Integration

Manages the review/approval flow for newsletters before publishing.
Writes newsletter content and status to a pending directory that the
BaileyAI approval bridge (launchd, 5-min cadence) picks up.

Flow:
1. Pipeline generates newsletter -> submit_for_review() writes to pending/
2. Approval bridge creates Gmail draft from pending content
3. User sends draft (approval) or deletes (rejection)
4. check_approval() returns status; mark_published() closes the loop
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("ahgen.governance")

BASE_DIR = Path(__file__).parent
PENDING_DIR = BASE_DIR / "pending-newsletter"


def _ensure_pending_dir() -> Path:
    """Create the pending-newsletter directory if it doesn't exist."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    return PENDING_DIR


def submit_for_review(
    newsletter_md: str,
    newsletter_html: str,
    date: str,
) -> Path:
    """Write newsletter to pending directory for human review.

    Args:
        newsletter_md: Markdown version of the newsletter.
        newsletter_html: HTML version for email/Substack.
        date: Date string (YYYY-MM-DD) used as the filename prefix.

    Returns:
        Path to the status file.
    """
    pending = _ensure_pending_dir()

    md_path = pending / "{}.md".format(date)
    html_path = pending / "{}.html".format(date)
    status_path = pending / "{}.status".format(date)
    meta_path = pending / "{}.meta.json".format(date)

    # Write content files
    md_path.write_text(newsletter_md, encoding="utf-8")
    html_path.write_text(newsletter_html, encoding="utf-8")

    # Write status
    status_path.write_text("pending", encoding="utf-8")

    # Write metadata
    word_count = len(newsletter_md.split())
    meta = {
        "date": date,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "source_count": 11,  # All Chinese scrapers
        "word_count_md": word_count,
        "char_count_md": len(newsletter_md),
        "char_count_html": len(newsletter_html),
        "status": "pending",
        "pipeline": "b2b",
    }
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    log.info(
        "Newsletter submitted for review: %s (%d words, status=pending)",
        date,
        word_count,
    )

    return status_path


def check_approval(date: str) -> Optional[str]:
    """Check if a newsletter has been approved, rejected, or is still pending.

    Args:
        date: Date string (YYYY-MM-DD) to check.

    Returns:
        'approved', 'rejected', 'published', 'pending', or None if no
        newsletter exists for that date.
    """
    status_path = PENDING_DIR / "{}.status".format(date)

    if not status_path.exists():
        return None

    status = status_path.read_text(encoding="utf-8").strip().lower()

    if status in ("approved", "rejected", "published", "pending"):
        return status

    log.warning("Unknown status '%s' for date %s, treating as pending", status, date)
    return "pending"


def mark_published(date: str) -> bool:
    """Mark a newsletter as published.

    Args:
        date: Date string (YYYY-MM-DD) to mark.

    Returns:
        True if successfully marked, False if no newsletter exists for that date.
    """
    status_path = PENDING_DIR / "{}.status".format(date)
    meta_path = PENDING_DIR / "{}.meta.json".format(date)

    if not status_path.exists():
        log.warning("Cannot mark published: no newsletter for %s", date)
        return False

    status_path.write_text("published", encoding="utf-8")

    # Update metadata
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["status"] = "published"
            meta["published_at"] = datetime.now(timezone.utc).isoformat()
            meta_path.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except (json.JSONDecodeError, IOError) as e:
            log.warning("Failed to update meta for %s: %s", date, e)

    log.info("Newsletter marked as published: %s", date)
    return True


def mark_approved(date: str) -> bool:
    """Mark a newsletter as approved (ready to publish).

    Args:
        date: Date string (YYYY-MM-DD) to mark.

    Returns:
        True if successfully marked, False if no newsletter exists.
    """
    status_path = PENDING_DIR / "{}.status".format(date)
    meta_path = PENDING_DIR / "{}.meta.json".format(date)

    if not status_path.exists():
        log.warning("Cannot mark approved: no newsletter for %s", date)
        return False

    status_path.write_text("approved", encoding="utf-8")

    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["status"] = "approved"
            meta["approved_at"] = datetime.now(timezone.utc).isoformat()
            meta_path.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except (json.JSONDecodeError, IOError) as e:
            log.warning("Failed to update meta for %s: %s", date, e)

    log.info("Newsletter marked as approved: %s", date)
    return True


def mark_rejected(date: str, reason: str = "") -> bool:
    """Mark a newsletter as rejected.

    Args:
        date: Date string (YYYY-MM-DD) to mark.
        reason: Optional rejection reason.

    Returns:
        True if successfully marked, False if no newsletter exists.
    """
    status_path = PENDING_DIR / "{}.status".format(date)
    meta_path = PENDING_DIR / "{}.meta.json".format(date)

    if not status_path.exists():
        log.warning("Cannot mark rejected: no newsletter for %s", date)
        return False

    status_path.write_text("rejected", encoding="utf-8")

    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["status"] = "rejected"
            meta["rejected_at"] = datetime.now(timezone.utc).isoformat()
            if reason:
                meta["rejection_reason"] = reason
            meta_path.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except (json.JSONDecodeError, IOError) as e:
            log.warning("Failed to update meta for %s: %s", date, e)

    log.info("Newsletter marked as rejected: %s (reason: %s)", date, reason or "none")
    return True


def list_pending() -> list:
    """List all pending newsletters.

    Returns:
        List of dicts with date and status for each newsletter.
    """
    if not PENDING_DIR.exists():
        return []

    results = []
    for status_file in sorted(PENDING_DIR.glob("*.status")):
        date = status_file.stem
        status = status_file.read_text(encoding="utf-8").strip().lower()
        meta_path = PENDING_DIR / "{}.meta.json".format(date)
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        results.append({
            "date": date,
            "status": status,
            "submitted_at": meta.get("submitted_at", ""),
            "word_count": meta.get("word_count_md", 0),
        })

    return results
