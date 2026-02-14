"""
Lex publish module — drains the publish_queue to LinkedIn, Dev.to, Medium.

Each publisher is a simple function that takes (title, body) and returns
a platform_id on success or raises on failure. The drain loop handles
retry logic via the db layer.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, Optional

from lib.db import get_publishable, mark_published, mark_publish_failed

log = logging.getLogger("lex.publish")


# ── Platform Publishers ──────────────────────────────────────

def publish_linkedin(body: str, title: Optional[str] = None) -> str:
    """Publish a text post to LinkedIn via API.

    Requires LINKEDIN_ACCESS_TOKEN env var (OAuth 2.0 bearer token).
    Returns the post URN as platform_id.
    """
    import httpx

    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("LINKEDIN_ACCESS_TOKEN not set")

    # LinkedIn UGC Post API (v2)
    # First get the person URN
    me_resp = httpx.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    me_resp.raise_for_status()
    person_sub = me_resp.json()["sub"]
    author = f"urn:li:person:{person_sub}"

    post_data = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": body[:3000]},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    resp = httpx.post(
        "https://api.linkedin.com/v2/ugcPosts",
        json=post_data,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.headers.get("x-restli-id", resp.json().get("id", "unknown"))


def publish_devto(body: str, title: Optional[str] = None) -> str:
    """Publish an article to Dev.to via API.

    Requires DEVTO_API_KEY env var.
    Returns the article ID as platform_id.
    """
    import httpx

    api_key = os.environ.get("DEVTO_API_KEY")
    if not api_key:
        raise RuntimeError("DEVTO_API_KEY not set")

    article_data = {
        "article": {
            "title": title or body[:60],
            "body_markdown": body,
            "published": True,
            "tags": ["ai", "china", "news"],
        }
    }

    resp = httpx.post(
        "https://dev.to/api/articles",
        json=article_data,
        headers={"api-key": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    return str(resp.json()["id"])


def publish_medium(body: str, title: Optional[str] = None) -> str:
    """Publish a post to Medium via API.

    Requires MEDIUM_INTEGRATION_TOKEN env var.
    Returns the post ID as platform_id.
    """
    import httpx

    token = os.environ.get("MEDIUM_INTEGRATION_TOKEN")
    if not token:
        raise RuntimeError("MEDIUM_INTEGRATION_TOKEN not set")

    # Get user ID first
    me_resp = httpx.get(
        "https://api.medium.com/v1/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    me_resp.raise_for_status()
    user_id = me_resp.json()["data"]["id"]

    post_data = {
        "title": title or body[:60],
        "contentFormat": "markdown",
        "content": body,
        "publishStatus": "public",
        "tags": ["artificial-intelligence", "china", "technology"],
    }

    resp = httpx.post(
        f"https://api.medium.com/v1/users/{user_id}/posts",
        json=post_data,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"]["id"]


# ── Publisher Registry ───────────────────────────────────────

PUBLISHERS = {
    "linkedin": publish_linkedin,
    "devto": publish_devto,
    "medium": publish_medium,
}


# ── Drain Loop ───────────────────────────────────────────────

def drain_queue(platform: Optional[str] = None, limit: int = 20) -> Dict:
    """Process publishable items from the queue.

    Tries the main body first. If that fails and fallback_body exists,
    tries the fallback. This is the "always publish" guarantee.

    Returns summary of results.
    """
    items = get_publishable(platform=platform, limit=limit)
    if not items:
        log.info("Publish queue empty")
        return {"published": 0, "failed": 0, "skipped": 0}

    log.info(f"Processing {len(items)} publish queue items")
    published = 0
    failed = 0
    skipped = 0

    for item in items:
        plat = item["platform"]
        publisher = PUBLISHERS.get(plat)

        if not publisher:
            log.warning(f"No publisher for platform '{plat}', skipping {item['id']}")
            skipped += 1
            continue

        # Check if platform API key is configured
        env_keys = {
            "linkedin": "LINKEDIN_ACCESS_TOKEN",
            "devto": "DEVTO_API_KEY",
            "medium": "MEDIUM_INTEGRATION_TOKEN",
        }
        if not os.environ.get(env_keys.get(plat, "")):
            log.info(f"[{plat}] API key not configured, skipping {item['id']}")
            skipped += 1
            continue

        # Try main body
        try:
            platform_id = publisher(item["body"], item.get("title"))
            mark_published(item["id"], platform_id)
            log.info(f"[{plat}] Published {item['id']} -> {platform_id}")
            published += 1
        except Exception as e:
            log.warning(f"[{plat}] Failed {item['id']}: {e}")

            # Try fallback body if available
            if item.get("fallback_body"):
                try:
                    platform_id = publisher(item["fallback_body"], item.get("title"))
                    mark_published(item["id"], platform_id)
                    log.info(f"[{plat}] Published {item['id']} via fallback -> {platform_id}")
                    published += 1
                    continue
                except Exception as fallback_err:
                    log.warning(f"[{plat}] Fallback also failed {item['id']}: {fallback_err}")
                    mark_publish_failed(item["id"], f"Primary: {e} | Fallback: {fallback_err}")
                    failed += 1
            else:
                mark_publish_failed(item["id"], str(e))
                failed += 1

    log.info(f"Drain complete: {published} published, {failed} failed, {skipped} skipped")
    return {"published": published, "failed": failed, "skipped": skipped}
