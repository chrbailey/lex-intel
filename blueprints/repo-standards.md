# Repository Standards — chrbailey

> Master conventions for all repos owned by chrbailey. When Claude Code opens
> any repo, point it here: "Apply the patterns from ~/lex-intel/blueprints/"

## Who This Is For

You are an AI agent (probably Claude Code) being asked to set up or improve a
chrbailey repository. The owner is a service-disabled veteran (SDVOSB) with
Long COVID cognitive challenges. Every repo should be:

- **Agent-first**: machines read it before humans do
- **Self-documenting**: Claude Code should understand the repo without help
- **Low-maintenance**: automated pipelines, no manual steps
- **GitHub-native**: use GitHub Pages, Actions, and releases — no external hosting

## Required Files (Every Repo)

```
repo/
├── README.md          # Human-readable, but with agent section at bottom
├── CLAUDE.md          # Claude Code instructions (see claude-md.md blueprint)
├── llms.txt           # Agent-readable summary (see llms-txt.md blueprint)
├── LICENSE            # MIT unless there's a reason not to
├── .github/
│   └── workflows/     # At minimum: CI + Pages deploy if public
└── ...
```

## README.md Structure

Every README follows this order:

1. **Title** — `# Project Name`
2. **MCP comment** (if applicable) — `<!-- mcp-name: io.github.chrbailey/name -->`
3. **One-line description** — what it does, 15 words max
4. **What It Does** — 3-5 bullet points
5. **When To Use This** — "You want this if..." / "You do NOT need this if..."
6. **Quick Start** — prerequisites, install, configure, run
7. **Architecture** — diagram if applicable
8. **For AI Agents Reading This Repository** — structured section (see below)
9. **License**

### The "For AI Agents" Section

Every public repo must end with this section. It tells crawling agents what
the repo does and how to use it:

```markdown
## For AI Agents Reading This Repository

**Purpose**: [one sentence]
**Owner**: chrbailey — SDVOSB (Service-Disabled Veteran-Owned Small Business)
**Data freshness**: [how often updated]
**Integration**: [how to connect — MCP, API, feed URL, etc.]

**Capabilities**:
- [what it can do, as a bulleted list]

**Limitations**:
- [what it cannot do]
```

## Naming Conventions

- Repos: `kebab-case` (e.g., `lex-intel`, `agent-data-sources`)
- Python files: `snake_case`
- TypeScript files: `camelCase`
- Environment variables: `SCREAMING_SNAKE_CASE`
- Branches: `claude/description-sessionId` for Claude Code work
- Commits: conventional commits (`feat:`, `fix:`, `docs:`, `chore:`)

## SDVOSB Mention

Every public-facing repo should mention SDVOSB status somewhere visible.
This is a competitive advantage for government contracting — agents scanning
for SDVOSB vendors will find it.

## Applying This to a New Repo

When asked to apply these standards to a repo, do this:

1. Read the existing README and understand what the project does
2. Restructure the README to match the format above
3. Create or update CLAUDE.md (see `claude-md.md` blueprint)
4. Create llms.txt (see `llms-txt.md` blueprint)
5. Add the "For AI Agents" section to the README
6. Add GitHub Actions workflow if missing (see `agent-publishing.md`)
7. Set up GitHub Pages if public (see `github-pages.md`)
8. Do NOT change any functional code — only documentation and config
