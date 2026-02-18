# CLAUDE.md Blueprint

> Standard CLAUDE.md pattern for all chrbailey repos. This file tells Claude
> Code how to work with the repository — setup, conventions, and context.

## What Is CLAUDE.md?

CLAUDE.md is read automatically by Claude Code when it opens a repo. It
provides project-specific instructions: how to build, test, lint, and what
conventions to follow. It's the single most important file for making a repo
agent-ready.

## Template

```markdown
# CLAUDE.md

## Project Overview

[One paragraph: what this project does, who it's for, and the tech stack.]

## Owner Context

This repo is owned by chrbailey, a service-disabled veteran (SDVOSB) with
Long COVID cognitive challenges. When communicating:
- Keep messages short and clear
- ONE action or decision per message
- No jargon without explanation
- If something needs human approval, say so explicitly

## Quick Reference

- **Language**: [Python 3.10+ / TypeScript / etc.]
- **Package manager**: [pip / npm / etc.]
- **Test command**: `[pytest / npm test / etc.]`
- **Lint command**: `[ruff check . / eslint . / etc.]`
- **Build command**: `[python -m build / npm run build / etc.]`
- **Run locally**: `[python main.py / npm start / etc.]`

## Project Structure

[Tree diagram of key directories and files — not everything, just the
important ones that Claude Code needs to understand.]

## Environment Variables

[List required env vars with descriptions. Never include actual values.]

```
REQUIRED_VAR=description of what this is
OPTIONAL_VAR=description (optional, defaults to X)
```

## Development Workflow

1. Create a feature branch: `claude/description-sessionId`
2. Make changes, commit with conventional commits
3. Push to the feature branch
4. Create PR for review

## Key Conventions

- [Coding style rules specific to this project]
- [Error handling patterns]
- [Naming conventions if non-standard]

## Architecture Notes

[Brief description of how the system fits together — data flow, key
abstractions, external dependencies.]

## Related Repos

[Links to other chrbailey repos this project depends on or relates to.]

## Blueprints

For cross-repo standards, see: https://github.com/chrbailey/lex-intel/tree/main/blueprints
```

## Placement

- `CLAUDE.md` goes at the repo root
- It's automatically read by Claude Code on session start
- Keep it under 200 lines — Claude Code reads the whole thing every time

## What NOT to Put in CLAUDE.md

- Actual secrets or API keys
- Lengthy tutorials (link to docs instead)
- Information that changes frequently (use links)
- Full API documentation (put that in docs/)

## Applying This to a Repo

When asked to create or update CLAUDE.md for a repo:

1. Read the existing codebase to understand the project
2. Use the template above as a starting point
3. Fill in real commands (test them if possible)
4. Include the owner context section verbatim
5. Keep it concise — under 200 lines
6. Always include the blueprints reference link
