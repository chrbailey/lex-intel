# Security

## Responsible Disclosure

If you find a security issue, please do **not** file a public GitHub issue.

Email: chris.bailey@erp-access.com — include "SECURITY: lex-intel" in the subject line.

Expect an acknowledgment within 72 hours.

## What this tool does

Lex Intel scrapes 11 public Chinese-language tech outlets, translates and categorizes articles with the Anthropic API, stores them in Supabase (Postgres) and Pinecone (vector index), and serves them through an MCP server. It optionally publishes generated briefings to Dev.to, Hashnode, and Blogger when credentials are configured.

The secrets surface: `ANTHROPIC_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `PINECONE_API_KEY`, and optional publishing keys (`DEVTO_API_KEY`, `HASHNODE_API_KEY`, `BLOGGER_EMAIL`). All live in `.env` (mode 600).

## What this tool does NOT do

- It does not store credentials in the database or vector index.
- It does not send scraped content to any third party other than the Anthropic API (for translation/categorization), Supabase (storage), Pinecone (embeddings), and the publisher platforms you have explicitly configured.
- It does not publish automatically to platforms you have not configured with keys — unconfigured platforms are skipped silently.
- It does not log or persist full article text beyond the first 10K characters per article.
- It does not perform any authenticated write operation against the scraped outlets (no login, no comments, no interaction).

## Known Considerations

- `SUPABASE_SERVICE_ROLE_KEY` bypasses row-level security. Anyone with this key has full read/write access to your Supabase project. Keep it out of logs and never commit it.
- The MCP server runs over stdio by default. If you expose it over HTTP via FastMCP, any client that reaches the port can call any of the 11 tools — put it behind auth.
- Translation/categorization sends article content to Anthropic. If you scrape a source with content that would violate Anthropic's usage policies, that's on you.
- Pinecone index `claude-knowledge-base`, namespace `lex-articles` is shared by default — if your deployment is multi-tenant, use a dedicated namespace.
- Publisher tokens in `.env` have write access to your published account. Treat them with the same care as a password.

If you see evidence of any of the "does NOT do" items, that is a security issue — please report.
