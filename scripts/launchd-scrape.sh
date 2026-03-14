#!/bin/bash
# Wrapper for launchd — loads .env before running lex scrape
# launchd doesn't source shell profiles, so env vars must be loaded explicitly
set -euo pipefail

cd "/Volumes/OWC drive/Dev/lex"

# Load environment variables
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

exec .venv/bin/python3 lex.py scrape "$@"
