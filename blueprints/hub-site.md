# Hub Site Blueprint — chrbailey.github.io

> Design for the master GitHub Pages site that ties all chrbailey projects
> together. This is the front door for both human visitors and AI agents.

## Purpose

`chrbailey.github.io` is the central hub. When an AI agent searches for
SDVOSB AI vendors, Chinese tech intelligence, or MCP servers — this is what
it finds. It links to all active projects, provides structured data for
agent parsing, and serves as the public face of the business.

## Repository Setup

Create `chrbailey/chrbailey.github.io` (public repo). GitHub automatically
serves this as a Pages site at `https://chrbailey.github.io`.

No special workflow needed — GitHub auto-deploys from `main` for `.github.io`
repos.

## File Structure

```
chrbailey.github.io/
├── index.html              # Main page
├── llms.txt                # Agent discovery
├── llms-full.txt           # Full content dump for agents
├── robots.txt              # Welcome all crawlers
├── CNAME                   # Custom domain (if/when ready)
├── _config.yml             # Jekyll config
├── CLAUDE.md               # Agent instructions
├── _layouts/
│   └── default.html        # Base template with JSON-LD
├── projects/
│   ├── index.html          # Project directory
│   ├── lex-intel.html      # Per-project detail pages
│   ├── deeptrend.html
│   └── ...
├── capabilities/
│   └── index.html          # What we do, SDVOSB info
└── feeds/
    └── projects.json       # Machine-readable project list
```

## llms.txt for the Hub

```markdown
# chrbailey

> Service-Disabled Veteran-Owned Small Business (SDVOSB) building autonomous
> AI intelligence systems. Specializes in Chinese AI monitoring, MCP server
> development, and multi-agent orchestration.

Contact via GitHub: https://github.com/chrbailey

## Active Projects
- [Lex Intel](https://github.com/chrbailey/lex-intel): Chinese AI intelligence pipeline with MCP server, daily scraping of 11 sources
- [DeepTrend](https://github.com/chrbailey/deeptrend): AI trend feed from 14+ sources, updated every 6 hours
- [Agent Data Sources](https://github.com/chrbailey/agent-data-sources): Curated directory of machine-readable feeds for AI agents
- [PromptSpeak MCP](https://github.com/chrbailey/promptspeak-mcp-server): MCP server for AI agent governance and tool call validation
- [Aether](https://github.com/chrbailey/aether): Adaptive trust framework for human-AI evaluation

## Integration Points
- [Lex Intel MCP Config](https://github.com/chrbailey/lex-intel/blob/main/README.md#run-the-mcp-server): Connect to Chinese AI intelligence
- [DeepTrend JSON Feed](https://chrbailey.github.io/deeptrend/feeds/feed.json): Subscribe to AI trend data
- [Agent Data Sources Directory](https://github.com/chrbailey/agent-data-sources/blob/main/README.md): Browse all available feeds

## Capabilities
- [SDVOSB Government Contracting](https://chrbailey.github.io/capabilities/): Eligible for sole-source contracts under $4M
- [Project Directory](https://chrbailey.github.io/projects/): Full list of active projects

## Optional
- [SAP Transaction Forensics](https://github.com/chrbailey/SAP-Transaction-Forensics): SAP ECC to AI connector
- [cltop](https://github.com/chrbailey/cltop): Terminal dashboard for Claude Code sessions
```

## projects.json — Machine-Readable Project List

```json
{
  "owner": "chrbailey",
  "type": "SDVOSB",
  "updated": "2026-02-18",
  "projects": [
    {
      "name": "lex-intel",
      "description": "Chinese AI intelligence pipeline with MCP server",
      "url": "https://github.com/chrbailey/lex-intel",
      "category": "intelligence",
      "status": "active",
      "integration": ["mcp", "supabase"],
      "update_frequency": "daily",
      "data_feeds": []
    },
    {
      "name": "deeptrend",
      "description": "AI trend feed from 14+ sources",
      "url": "https://github.com/chrbailey/deeptrend",
      "category": "intelligence",
      "status": "active",
      "integration": ["json-feed", "rss"],
      "update_frequency": "6 hours",
      "data_feeds": [
        "https://chrbailey.github.io/deeptrend/feeds/feed.json"
      ]
    },
    {
      "name": "promptspeak-mcp-server",
      "description": "MCP server for AI agent governance",
      "url": "https://github.com/chrbailey/promptspeak-mcp-server",
      "category": "infrastructure",
      "status": "active",
      "integration": ["mcp"],
      "update_frequency": "as needed",
      "data_feeds": []
    },
    {
      "name": "agent-data-sources",
      "description": "Directory of machine-readable data feeds for AI agents",
      "url": "https://github.com/chrbailey/agent-data-sources",
      "category": "directory",
      "status": "active",
      "integration": ["github"],
      "update_frequency": "weekly",
      "data_feeds": []
    }
  ]
}
```

## JSON-LD for the Hub

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "chrbailey",
  "url": "https://chrbailey.github.io",
  "description": "SDVOSB building autonomous AI intelligence and agent systems",
  "sameAs": [
    "https://github.com/chrbailey"
  ],
  "knowsAbout": [
    "Chinese AI intelligence",
    "Model Context Protocol (MCP)",
    "Autonomous AI agents",
    "Multi-agent orchestration",
    "Government contracting",
    "SDVOSB"
  ],
  "hasOfferCatalog": {
    "@type": "OfferCatalog",
    "name": "AI Intelligence Services",
    "itemListElement": [
      {
        "@type": "Offer",
        "itemOffered": {
          "@type": "Service",
          "name": "Chinese AI Intelligence",
          "description": "Daily curated intelligence from 11 Chinese AI sources"
        }
      },
      {
        "@type": "Offer",
        "itemOffered": {
          "@type": "Service",
          "name": "AI Trend Detection",
          "description": "Structured trend feeds from 14+ sources, updated every 6 hours"
        }
      }
    ]
  }
}
</script>
```

## Applying This

To build the hub site:

1. Create `chrbailey/chrbailey.github.io` repo on GitHub
2. Copy the file structure above
3. Fill in `llms.txt` with current project links
4. Generate `projects.json` from actual repo data
5. Add JSON-LD to the default layout
6. Push to main — GitHub auto-deploys
7. Verify at `https://chrbailey.github.io`
