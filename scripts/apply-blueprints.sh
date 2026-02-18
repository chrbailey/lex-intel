#!/usr/bin/env bash
# apply-blueprints.sh — Apply lex-intel blueprints to all chrbailey repos
#
# Usage:
#   ./scripts/apply-blueprints.sh              # all repos
#   ./scripts/apply-blueprints.sh deeptrend    # single repo
#   DRY_RUN=1 ./scripts/apply-blueprints.sh    # preview only
#
# Prerequisites:
#   - claude CLI installed and authenticated
#   - gh CLI installed and authenticated
#   - ~/lex-intel/blueprints/ exists (this repo)

set -euo pipefail

GITHUB_USER="chrbailey"
BLUEPRINTS_DIR="${HOME}/lex-intel/blueprints"
WORKSPACE="${HOME}/repos"
DRY_RUN="${DRY_RUN:-0}"

# All repos to standardize (skip lex-intel — it's the source)
ALL_REPOS=(
  deeptrend
  agent-data-sources
  promptspeak-mcp-server
  promptspeak-ai-sdk
  aether
  epistemic-flow-control
  MyPersona
  cltop
  prompt-optimizer
  ahgen-presence
  SAP-Transaction-Forensics
  daily-heat
  restaurant-scheduler
  word-drop
)

# Repos that should get GitHub Pages (public, produce content)
PAGES_REPOS=(
  deeptrend
  agent-data-sources
  ahgen-presence
  promptspeak-mcp-server
  aether
)

# ── Helpers ──────────────────────────────────────────────────────────────

log()  { echo -e "\033[1;34m[blueprint]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[done]\033[0m $*"; }
warn() { echo -e "\033[1;33m[skip]\033[0m $*"; }
err()  { echo -e "\033[1;31m[error]\033[0m $*"; }

ensure_cloned() {
  local repo=$1
  local dir="${WORKSPACE}/${repo}"
  if [ -d "$dir" ]; then
    log "Updating ${repo}..."
    git -C "$dir" pull --ff-only origin main 2>/dev/null || true
  else
    log "Cloning ${repo}..."
    gh repo clone "${GITHUB_USER}/${repo}" "$dir" 2>/dev/null || {
      err "Could not clone ${repo} — skipping"
      return 1
    }
  fi
  return 0
}

should_get_pages() {
  local repo=$1
  for pr in "${PAGES_REPOS[@]}"; do
    [ "$pr" = "$repo" ] && return 0
  done
  return 1
}

apply_to_repo() {
  local repo=$1
  local dir="${WORKSPACE}/${repo}"

  log "━━━ Processing: ${repo} ━━━"

  if ! ensure_cloned "$repo"; then
    return
  fi

  # Build the prompt for Claude Code
  local pages_instruction=""
  if should_get_pages "$repo"; then
    pages_instruction="This is a public repo that should get GitHub Pages. Also apply github-pages.md and agent-publishing.md blueprints."
  fi

  local prompt="You are standardizing this repository using the chrbailey blueprints.

READ these blueprint files first:
- ${BLUEPRINTS_DIR}/repo-standards.md
- ${BLUEPRINTS_DIR}/claude-md.md
- ${BLUEPRINTS_DIR}/llms-txt.md
${pages_instruction}

Then apply them to THIS repo. Specifically:
1. Read the existing README.md and all key files to understand what this project does
2. Restructure the README to match the repo-standards.md format (keep all existing content, just reorganize and add the 'For AI Agents' section)
3. Create or update CLAUDE.md using the claude-md.md template
4. Create llms.txt using the llms-txt.md template with REAL links to this repo's actual files
5. Do NOT change any functional code — only documentation and config files
6. Commit with message: 'docs: apply chrbailey blueprint standards'
7. Push to main

IMPORTANT: Do not delete or lose any existing content. Only add structure and new files."

  if [ "$DRY_RUN" = "1" ]; then
    log "[DRY RUN] Would run Claude Code in: ${dir}"
    log "[DRY RUN] Prompt: ${prompt:0:100}..."
    return
  fi

  # Run Claude Code in the repo directory
  cd "$dir"
  echo "$prompt" | claude --dangerously-skip-permissions -p 2>&1 | tee "/tmp/blueprint-${repo}.log"
  local exit_code=$?

  if [ $exit_code -eq 0 ]; then
    ok "${repo} — blueprints applied"
  else
    err "${repo} — Claude Code exited with code ${exit_code}"
    err "Check /tmp/blueprint-${repo}.log for details"
  fi

  cd - > /dev/null
}

# ── Main ─────────────────────────────────────────────────────────────────

main() {
  log "Blueprint applicator for chrbailey repos"
  log "Blueprints dir: ${BLUEPRINTS_DIR}"
  log "Workspace: ${WORKSPACE}"
  [ "$DRY_RUN" = "1" ] && warn "DRY RUN MODE — no changes will be made"
  echo ""

  # Verify prerequisites
  if ! command -v claude &>/dev/null; then
    err "claude CLI not found. Install: npm install -g @anthropic-ai/claude-code"
    exit 1
  fi
  if ! command -v gh &>/dev/null; then
    err "gh CLI not found. Install: brew install gh"
    exit 1
  fi
  if [ ! -d "$BLUEPRINTS_DIR" ]; then
    err "Blueprints not found at ${BLUEPRINTS_DIR}"
    err "Clone lex-intel first: gh repo clone ${GITHUB_USER}/lex-intel ~/lex-intel"
    exit 1
  fi

  mkdir -p "$WORKSPACE"

  # Process specific repo or all
  if [ $# -gt 0 ]; then
    for repo in "$@"; do
      apply_to_repo "$repo"
    done
  else
    local total=${#ALL_REPOS[@]}
    local count=0
    for repo in "${ALL_REPOS[@]}"; do
      count=$((count + 1))
      log "(${count}/${total})"
      apply_to_repo "$repo"
      echo ""
    done
  fi

  echo ""
  ok "All done. Check /tmp/blueprint-*.log for details."
}

main "$@"
