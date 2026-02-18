# Agent Publishing Blueprint

> How to set up automated publishing pipelines so agents can generate content
> and push it to GitHub Pages, feeds, or external platforms — without human
> intervention for routine output.

## The Pattern

```
Agent generates content (markdown/JSON)
  → Commits to repo
  → GitHub Actions triggers
  → Site/feed rebuilds automatically
  → Content is live on the web
```

No human in the loop for routine publishing. Human approval only for:
- Content that represents the business publicly (proposals, client comms)
- Financial commitments
- Anything flagged `requires_human: true`

## GitHub Actions: Auto-Publish on Push

This workflow rebuilds the site whenever new content is pushed to `main`:

### `.github/workflows/publish.yml`

```yaml
name: Publish Agent Output

on:
  push:
    branches: [main]
    paths:
      - 'public/reports/**'
      - 'public/feeds/**'
      - 'public/index.html'
  schedule:
    # Rebuild daily at 08:00 UTC even if nothing changed
    - cron: '0 8 * * *'
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Generate feeds
        run: |
          python scripts/generate_feeds.py

      - uses: actions/configure-pages@v5
      - uses: actions/jekyll-build-pages@v1
        with:
          source: ./public
      - uses: actions/upload-pages-artifact@v3

      - uses: actions/deploy-pages@v4
```

## Feed Generation Script

Every data project should generate machine-readable feeds. Template:

### `scripts/generate_feeds.py`

```python
"""Generate JSON Feed and RSS from published reports."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

SITE_URL = os.getenv("SITE_URL", "https://chrbailey.github.io/REPO_NAME")
REPORTS_DIR = Path("public/reports")
FEEDS_DIR = Path("public/feeds")


def generate_json_feed():
    """Generate JSON Feed 1.1 from report files."""
    items = []
    for report in sorted(REPORTS_DIR.glob("*.md"), reverse=True)[:50]:
        content = report.read_text()
        title = content.split("\n")[0].lstrip("# ")
        items.append({
            "id": f"{SITE_URL}/reports/{report.stem}",
            "url": f"{SITE_URL}/reports/{report.stem}.html",
            "title": title,
            "content_text": content,
            "date_published": datetime.fromtimestamp(
                report.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
        })

    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "REPO_NAME — chrbailey",
        "home_page_url": SITE_URL,
        "feed_url": f"{SITE_URL}/feeds/feed.json",
        "description": "DESCRIPTION",
        "authors": [{"name": "chrbailey", "url": "https://github.com/chrbailey"}],
        "items": items,
    }

    FEEDS_DIR.mkdir(parents=True, exist_ok=True)
    (FEEDS_DIR / "feed.json").write_text(json.dumps(feed, indent=2))


if __name__ == "__main__":
    generate_json_feed()
    print(f"Generated feed with {len(list(REPORTS_DIR.glob('*.md')))} items")
```

## Agent Commit Pattern

When an agent generates a report and wants to publish it:

```python
import subprocess
from datetime import date

def publish_report(title: str, content: str):
    """Write a report file and commit it for auto-publishing."""
    slug = title.lower().replace(" ", "-")[:50]
    filename = f"public/reports/{date.today().isoformat()}-{slug}.md"

    with open(filename, "w") as f:
        f.write(f"# {title}\n\n{content}")

    subprocess.run(["git", "add", filename], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"docs: publish {title}"],
        check=True,
    )
    subprocess.run(["git", "push"], check=True)
    # GitHub Actions auto-deploys from here
```

## Publishing to External Platforms

For cross-posting to Dev.to, Hashnode, LinkedIn, etc., lex-intel already has
this built into `lib/publish.py`. The pattern:

1. Agent generates content → stores in Supabase publish queue
2. `lex.py publish` drains the queue to configured platforms
3. Each platform has its own adapter (API, GraphQL, email)

To add this to another repo, copy the publish queue pattern from lex-intel
or simply have the agent commit markdown to the public repo and let GitHub
Pages handle distribution.

## Listing in agent-data-sources

After setting up a feed, add it to the
[agent-data-sources](https://github.com/chrbailey/agent-data-sources) directory
so other agents can discover it.

## Applying This to a Repo

When asked to set up agent publishing for a repo:

1. Create `scripts/generate_feeds.py` adapted to the project's output format
2. Create `public/reports/` directory with a `.gitkeep`
3. Add the GitHub Actions workflow
4. Generate initial `feed.json` and `feed.xml`
5. Add the feed URLs to `llms.txt`
6. Update `agent-data-sources` repo with the new feed
