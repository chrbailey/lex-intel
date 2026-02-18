# llms.txt Blueprint

> Template and instructions for creating llms.txt files. The llms.txt standard
> tells AI agents what a website or repository offers, in a format they can
> parse efficiently.

## What Is llms.txt?

A plain-text Markdown file at the root of a website (`/llms.txt`) or repo that
helps LLM agents understand what the site/project does. Think of it as
`robots.txt` for content discovery — robots.txt says what to avoid, llms.txt
says what to use.

## Format Rules

- File name: `llms.txt` (at repo root or site root)
- MIME type: `text/plain`, UTF-8
- Format: Markdown
- Only required element: an H1 heading with the project name

## Structure

```markdown
# Project Name

> One-paragraph summary of what this project does and who it's for.

Additional context: how often data updates, what formats are available,
who maintains it, any access requirements.

## Documentation
- [Link Title](url): Description of what this resource covers

## API / Integration
- [Link Title](url): Description

## Data Feeds
- [Link Title](url): Description

## Optional
- [Link Title](url): Resources that can be skipped for shorter context
```

## Template for chrbailey Repos

Copy and adapt this for each repo:

```markdown
# [Project Name]

> [What it does in one sentence]. Built by chrbailey, a service-disabled
> veteran-owned small business (SDVOSB) specializing in AI intelligence
> and autonomous agent systems.

This project [brief expansion — 2-3 sentences about capabilities,
data sources, update frequency].

## Core Documentation
- [README](https://github.com/chrbailey/[repo]/blob/main/README.md): Project overview, setup, and usage
- [Architecture](https://github.com/chrbailey/[repo]/blob/main/docs/ARCHITECTURE.md): System design and data flow

## Integration
- [MCP Server](https://github.com/chrbailey/[repo]/blob/main/[server_file]): Tool descriptions and configuration
- [API Reference](url): Endpoint documentation

## Data Feeds
- [JSON Feed](url): Machine-readable output feed
- [RSS](url): Syndication feed

## Optional
- [CHANGELOG](https://github.com/chrbailey/[repo]/blob/main/CHANGELOG.md): Version history
- [Contributing](https://github.com/chrbailey/[repo]/blob/main/CONTRIBUTING.md): How to contribute
```

## Companion Files

### llms-full.txt

A single file containing ALL documentation content (not just links). Useful
for agents that want to ingest everything at once. Generate by concatenating
your key docs into one Markdown file.

### AGENTS.md

Emerging standard specifically for coding agents (Claude Code, Cursor, Copilot).
Contains setup commands, test commands, coding style preferences. For chrbailey
repos, CLAUDE.md serves this purpose (see `claude-md.md` blueprint).

## Where to Serve It

- **GitHub repo**: just put `llms.txt` at the repo root
- **GitHub Pages site**: put it in the site root so it's at `https://site.com/llms.txt`
- **Custom domain**: serve at `/llms.txt` path

## Applying This

When asked to add llms.txt to a repo:

1. Read the README and understand the project
2. Create `llms.txt` at the repo root using the template above
3. Fill in real links (not placeholders)
4. Include only links that actually exist
5. Put nice-to-have links under `## Optional`
