# Lex Intel — Chinese AI Intelligence for AI Agents

<!-- mcp-name: io.github.chrbailey/lex-intel -->

**MCP server that gives AI agents access to curated Chinese AI/tech intelligence.** Daily signals from 11 Chinese-language sources (36Kr, Huxiu, CSDN, Caixin, Zhidx, and more), translated to English, scored by relevance, and served through semantic search.

## When to Use This

- Your agent needs to answer "What's happening in Chinese AI?"
- You're researching Chinese tech companies, funding, regulation, or breakthroughs
- You want daily briefings on Chinese AI developments in Bloomberg-style format
- You need trend analysis: which categories of Chinese AI are rising or declining

## Quick Start

```bash
pip install lex-intel
```

Add to your MCP client config:
```json
{
  "mcpServers": {
    "lex-intel": {
      "command": "lex-intel",
      "env": {
        "SUPABASE_URL": "your-url",
        "SUPABASE_ANON_KEY": "your-key",
        "PINECONE_API_KEY": "your-key"
      }
    }
  }
}
```

## Tools

### Read Tools

| Tool | When To Call It |
|------|----------------|
| `lex_search_articles` | Search for articles about a topic, company, or technology in Chinese AI |
| `lex_get_briefing` | Get the latest daily Bloomberg-style briefing (LEAD/PATTERNS/SIGNALS/WATCHLIST/DATA) |
| `lex_get_signals` | Find high-relevance (4-5) developments from recent days, grouped by category |
| `lex_get_trending` | See which Chinese AI categories have rising or declining coverage momentum |
| `lex_list_sources` | Check which sources are active and their signal quality |
| `lex_get_article` | Get full article details (body text, URL) after finding it via search |
| `lex_get_status` | Check pipeline health — latest run, queue depths, article counts |

### Write Tools (modify database, call external APIs)

| Tool | When To Call It |
|------|----------------|
| `lex_run_scrape` | Fetch new articles from all 11 sources + Gmail newsletters |
| `lex_run_analyze` | Translate, categorize, generate briefing, queue posts for publishing |
| `lex_run_publish` | Drain publish queue to configured platforms (Dev.to, Hashnode, Blogger, LinkedIn) |
| `lex_run_cycle` | Full pipeline: scrape → analyze → publish (skips if no new articles) |

## Data Sources

11 Chinese-language outlets scraped daily:
36Kr, Huxiu, InfoQ China, CSDN, SAP China, Kingdee, Yonyou, Leiphone, Caixin, Jiemian, Zhidx

Plus Gmail newsletters from Chinese tech sources.

## Categories

Articles are classified into 13 categories:
`funding`, `m_and_a`, `investment`, `product`, `regulation`, `breakthrough`, `research`, `open_source`, `partnership`, `adoption`, `personnel`, `market`, `other`

Each article is scored 1-5 for relevance to enterprise AI/tech readers.

## License

MIT
