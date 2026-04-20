# Contributing

Thanks for looking.

## Before opening a PR

1. **Open an issue first** for anything larger than a typo.
2. **All changes need tests.** If tests don't exist yet, at minimum add a test alongside your change.
3. **Match the existing code style.** Match language version, imports, naming.
4. **Run the full test suite locally** before submitting.

## What this project will not accept

Lex Intel is an MCP server plus a scrape → translate → categorize → publish pipeline for Chinese AI/tech intelligence. Changes that compromise the data integrity or expand the attack surface are not accepted.

- PRs that add new source sites without respecting robots.txt or that hit sites at rates that could look like abuse.
- PRs that alter or remove deduplication (exact-title Supabase check + Pinecone semantic dedup at 0.85). Duplicate suppression is a correctness requirement, not an optimization.
- PRs that remove Bloomberg-style brief structure (LEAD / PATTERNS / SIGNALS / WATCHLIST / DATA) without discussion. The format is the product.
- PRs that make translation pipelines call LLMs other than the configured provider without an explicit opt-in.
- PRs that bypass the publisher platform opt-in behavior (unconfigured platforms must be silently skipped — never auto-configured).
- Python 3.10+ is required. Do not add 3.11-only syntax without bumping the floor in `pyproject.toml`.

## Reporting security issues

See [SECURITY.md](SECURITY.md). Do not file security issues in the public tracker.

## Author

[Christopher Bailey](https://github.com/chrbailey).
