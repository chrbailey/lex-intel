#!/bin/bash
# Wrapper for launchd — loads .env before running lex publish
set -euo pipefail

cd "/Volumes/OWC drive/Dev/lex"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

exec .venv/bin/python3 lex.py publish "$@"
