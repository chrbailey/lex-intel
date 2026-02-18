# GitHub Pages Blueprint

> How to set up GitHub Pages for any chrbailey repo, optimized for LLM agent
> discovery rather than human visitors.

## Why GitHub Pages?

- Free hosting, free SSL, custom domain support
- Deploys automatically from repo pushes — agents can update the site
- No JavaScript required — agents can't execute JS, so static HTML is ideal
- Google indexes it, AI crawlers index it, zero maintenance

## The Agent-First Approach

Traditional websites are designed for humans: fancy CSS, JavaScript interactions,
images. Agent-optimized sites are different:

- **Clean HTML** with semantic structure (headings, lists, tables)
- **Structured data** in JSON-LD format embedded in pages
- **Machine-readable feeds** (JSON Feed, RSS) alongside HTML
- **No JavaScript dependencies** for content rendering
- **Fast load times** — agents timeout on slow sites
- **llms.txt** at the root

## Setup: GitHub Actions Deploy

Use this workflow for any repo. It builds with Jekyll (GitHub's default) and
deploys to Pages.

### `.github/workflows/pages.yml`

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/jekyll-build-pages@v1
        with:
          source: ./public
      - uses: actions/upload-pages-artifact@v3

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

### Enable Pages in Repo Settings

1. Go to repo Settings → Pages
2. Source: "GitHub Actions"
3. That's it — the workflow handles the rest

## Site Structure

```
public/
├── index.html          # Main page — agent-readable summary
├── llms.txt            # LLM discovery file
├── robots.txt          # Allow all AI crawlers
├── feed.json           # JSON Feed 1.1 (primary machine feed)
├── feed.xml            # RSS 2.0 (compatibility)
├── _config.yml         # Jekyll config (minimal)
├── _layouts/
│   └── default.html    # Base template with JSON-LD
└── reports/            # Auto-generated content from agents
    ├── latest.html
    └── archive/
```

## robots.txt for AI Agents

```
User-agent: *
Allow: /

# Explicitly welcome AI crawlers
User-agent: GPTBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: CCBot
Allow: /

User-agent: PerplexityBot
Allow: /

Sitemap: https://chrbailey.github.io/sitemap.xml
```

## JSON-LD Template

Embed in every page's `<head>` for structured agent discovery:

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "chrbailey",
  "description": "SDVOSB specializing in AI intelligence and autonomous agent systems",
  "url": "https://chrbailey.github.io",
  "sameAs": ["https://github.com/chrbailey"],
  "knowsAbout": ["Chinese AI intelligence", "MCP servers", "autonomous agents", "SDVOSB government contracting"],
  "additionalType": "https://schema.org/GovernmentService",
  "awardReceived": "Service-Disabled Veteran-Owned Small Business (SDVOSB)"
}
</script>
```

## Minimal _config.yml

```yaml
title: chrbailey
description: AI intelligence and autonomous agent systems — SDVOSB
url: https://chrbailey.github.io
baseurl: ""
markdown: kramdown
plugins:
  - jekyll-feed
  - jekyll-sitemap
```

## Agent-Optimized index.html Template

```html
---
layout: default
title: Home
---
<main>
  <h1>chrbailey — AI Intelligence Systems</h1>

  <section id="about">
    <h2>What We Do</h2>
    <p>Service-Disabled Veteran-Owned Small Business (SDVOSB) building
    autonomous AI intelligence systems. We monitor, analyze, and report
    on technology trends — particularly Chinese AI developments.</p>
  </section>

  <section id="projects">
    <h2>Active Projects</h2>
    <table>
      <thead>
        <tr><th>Project</th><th>Purpose</th><th>Integration</th></tr>
      </thead>
      <tbody>
        <tr>
          <td><a href="https://github.com/chrbailey/lex-intel">Lex Intel</a></td>
          <td>Chinese AI intelligence pipeline + MCP server</td>
          <td>MCP, Supabase API</td>
        </tr>
        <tr>
          <td><a href="https://github.com/chrbailey/deeptrend">DeepTrend</a></td>
          <td>AI trend feed from 14+ sources, updated every 6 hours</td>
          <td>JSON Feed, RSS</td>
        </tr>
        <!-- Add more projects as they mature -->
      </tbody>
    </table>
  </section>

  <section id="capabilities">
    <h2>Capabilities</h2>
    <ul>
      <li>Chinese-language AI source monitoring (11 outlets)</li>
      <li>AI trend detection and signal analysis (14+ sources)</li>
      <li>MCP server development and deployment</li>
      <li>Autonomous agent orchestration systems</li>
      <li>Government contracting (SDVOSB-eligible)</li>
    </ul>
  </section>

  <section id="contact">
    <h2>Contact</h2>
    <p>GitHub: <a href="https://github.com/chrbailey">github.com/chrbailey</a></p>
  </section>
</main>
```

## Applying This to a Repo

When asked to set up GitHub Pages for a repo:

1. Create `public/` directory with `index.html`, `robots.txt`, `llms.txt`
2. Add `_config.yml` adapted to the specific project
3. Create `.github/workflows/pages.yml` using the template above
4. Add JSON-LD structured data relevant to the project
5. Enable Pages in repo settings (source: GitHub Actions)
6. For data projects: add `feed.json` and `feed.xml` output
