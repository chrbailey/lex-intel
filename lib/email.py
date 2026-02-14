"""
Lex email delivery — sends briefings via Gmail API.

Uses Ahgen's Gmail OAuth credentials (config.json) for authentication.
Converts markdown briefing to HTML before sending.
"""
from __future__ import annotations

import base64
import logging
import os
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from lib.db import mark_briefing_emailed

log = logging.getLogger("lex.email")

# Ahgen's config.json stores Gmail OAuth tokens
AHGEN_DIR = Path("/Volumes/OWC drive/Dev/ahgen")

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


def _get_gmail_credentials() -> Optional[Credentials]:
    """Get valid Gmail credentials from Ahgen's config.json, refreshing if needed."""
    import json

    config_path = AHGEN_DIR / "config.json"
    if not config_path.exists():
        log.warning(f"Ahgen config.json not found at {config_path}")
        return None

    config = json.loads(config_path.read_text())

    if "gmail_token" not in config:
        log.warning("No gmail_token in Ahgen config.json — run Ahgen's Gmail OAuth setup first")
        return None

    from datetime import datetime
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
            # Save refreshed token back to Ahgen's config
            config["gmail_token"] = creds.token
            config["gmail_token_expiry"] = creds.expiry.isoformat() if creds.expiry else None
            config_path.write_text(json.dumps(config, indent=2))
            log.info("Gmail token refreshed")
        except Exception as e:
            log.error(f"Failed to refresh Gmail token: {e}")
            return None

    return creds


def _markdown_to_html(md_text: str) -> str:
    """Convert briefing markdown to styled HTML email.

    TODO(human): Implement markdown-to-HTML conversion with email styling.
    """
    # Placeholder — returns pre-formatted text wrapped in basic HTML
    escaped = md_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<html><body>
<pre style="font-family: Georgia, serif; font-size: 14px; line-height: 1.6; white-space: pre-wrap;">
{escaped}
</pre>
</body></html>"""


def send_briefing(
    briefing_text: str,
    briefing_id: str,
    to: Optional[str] = None,
    subject_prefix: str = "Lex Briefing",
) -> bool:
    """Send a briefing email via Gmail API.

    Args:
        briefing_text: Markdown briefing content
        briefing_id: Supabase briefing ID (marked as emailed on success)
        to: Recipient email (defaults to LEX_EMAIL_TO env var)
        subject_prefix: Email subject prefix

    Returns True on success.
    """
    recipient = to or os.environ.get("LEX_EMAIL_TO")
    if not recipient:
        log.warning("No email recipient — set LEX_EMAIL_TO in .env")
        return False

    creds = _get_gmail_credentials()
    if not creds:
        return False

    # Build email
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"{subject_prefix} — {today}"

    msg = MIMEMultipart("alternative")
    msg["To"] = recipient
    msg["Subject"] = subject

    # Plain text version
    msg.attach(MIMEText(briefing_text, "plain"))
    # HTML version
    msg.attach(MIMEText(_markdown_to_html(briefing_text), "html"))

    try:
        service = build("gmail", "v1", credentials=creds)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(
            userId="me",
            body={"raw": raw},
        ).execute()

        mark_briefing_emailed(briefing_id)
        log.info(f"Briefing {briefing_id} emailed to {recipient}")
        return True

    except Exception as e:
        log.error(f"Gmail send failed: {e}")
        return False
