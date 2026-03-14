#!/bin/bash
# Lex daily cycle: scrape → analyze → publish → site → push
# Called by launchd (com.erpaccess.lex-publish)

set -euo pipefail
cd "/Volumes/OWC drive/Dev/lex"

# Load environment variables (launchd doesn't source shell profiles)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Run the full pipeline (includes site generation as Phase 4)
.venv/bin/python3 lex.py cycle

# Commit and push docs/ if anything changed
if git diff --quiet docs/ 2>/dev/null; then
    echo "No docs changes to push"
else
    git add docs/
    git commit -m "chore: update daily briefing $(date +%Y-%m-%d)"
    git push origin main
    echo "Pushed docs update to GitHub"
fi
