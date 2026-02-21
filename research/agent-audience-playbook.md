# Publishing for Agent Audiences: Research & Playbook

> **Goal**: Get our content discovered, cited, and redistributed by AI agents — not humans directly. Agents filter to humans.

**Research date**: 2026-02-15
**Sources**: 3-agent parallel research swarm, 80+ web sources, ArXiv papers, GitHub data

---

## Part 1: Where Agents Actually Consume Content

### The Content Consumption Map

| Channel | Agent Activity | Evidence Quality | Our Current Presence |
|---------|---------------|-----------------|---------------------|
| **Reddit** | ~40-47% of Perplexity citations | Citation studies, Reddit lawsuits | None |
| **Wikipedia** | ~16-48% of ChatGPT citations | Citation studies (177M citations) | None |
| **YouTube** | ~23% across platforms | Semrush/Ahrefs studies | None |
| **GitHub** | 15-22% project adoption by agents | Academic study, 129K projects | PromptSpeak (public), touchgrass (public) |
| **LinkedIn** | 53.7% of long posts are AI-generated; rising citations | Originality.ai 3,368-post study | Minimal |
| **Medium/Dev.to** | Growing AI-written + AI-cited | Lex publishes to Dev.to | Active via Lex (Dev.to) |
| **Stack Overflow** | Splits "how-to" citations with YouTube | Citation pattern studies | None |
| **MCP Registries** | 17,186+ servers on mcp.so alone | Registry counts, official spec | Not registered |
| **npm/PyPI** | Primary discovery via training data | Package registry analysis | npm prepped, not published |
| **RSS/Atom feeds** | NLWeb + agent consumption confirmed | Microsoft NLWeb, RSS still consumed | Not configured |
| **llms.txt** | 844K websites adopted; unproven impact | Contradictory evidence | Not implemented |

### Key Data Points

- **Reddit with 3+ upvotes = Tier 2 training data for OpenAI** (after Wikipedia/licensed partners)
- **ChatGPT increased citation source diversity by 80% in 2 months** (Aug-Oct 2025)
- **90% of ChatGPT citations come from positions 21+** in traditional search — Google ranking barely matters
- **AI search visitors convert at 4.4x** the rate of traditional organic visitors
- **AI referral sessions jumped 527%** between Jan-May 2025
- **7 of top 10 most-cited domains are UGC platforms**: Reddit, Wikipedia, YouTube, LinkedIn, Medium, Stack Overflow, Quora

---

## Part 2: How Agents Discover and Cite Content

### What Gets Cited (Hard Data)

| Signal | Impact | Source |
|--------|--------|--------|
| Brand web mentions | 0.664 correlation (strongest) | ConvertMate 2026 study |
| Content freshness (≤30 days) | 3.2x more citations | Multiple studies |
| 50-150 word self-contained chunks | 2.3x more citations | Digital Bloom, StoryChief |
| FAQPage schema markup | 41% vs 15% citation rate (2.7x) | Relixir 2025 |
| Original data/statistics | 30-40% higher visibility | Princeton GEO paper (SIGKDD 2024) |
| Comparison tables | 32.5% of citations lead with comparisons | Averi.ai |
| Inline citations to sources | ~40% improvement | GEO paper |
| 50+ referring domains | 5x more AI traffic | Superprompt study |
| Articles with pull quotes + stats | 37% increase in citation rate | Digital Bloom |
| Content updated with visible timestamp | Required for freshness signal | Multiple |

### What Doesn't Matter (Counter-Intuitive)

- **Google search ranking**: Weak correlation with LLM citation. Sites #1 on Google often ignored by AI.
- **Backlinks**: Contradicts decades of SEO wisdom — weak/neutral signal for LLMs.
- **llms.txt**: No LLM provider confirmed they read it. Statistical analysis shows no effect.
- **JavaScript-rendered content**: Most AI crawlers don't render JS. Invisible to them.

### The GEO Paper (Princeton/Georgia Tech, SIGKDD 2024)

Tested 9 optimization methods on 10,000 queries. Top 3 methods:

1. **Cite Sources**: ~40% improvement in position-adjusted visibility
2. **Quotation Addition**: ~35% improvement
3. **Statistics Addition**: ~30% improvement

Key insight: These require **minimal content changes** — they add credibility signals, not new information.

---

## Part 3: Agent Infrastructure — Where Agents Live

### GitHub: The Agent Workspace

- **15-22% of GitHub projects** now show coding agent adoption (arXiv study, 129K projects)
- **83.8% of agent-assisted PRs** are eventually merged
- **54.9% merged without human modification**
- AGENTS.md adopted by **60,000+ repositories** — the "README for coding agents"
- GitHub Copilot, Devin, OpenHands, SWE-Agent, Gemini CLI all active

**Agent-friendly repo requirements:**
1. AGENTS.md in root (build/test/convention instructions)
2. .github/copilot-instructions.md (Copilot-specific)
3. Clear README (problem → solution → usage)
4. Comprehensive test suites (agents verify their changes)
5. CI/CD agents can observe

### MCP Registries: Agent Tool Discovery

| Registry | Server Count | Status |
|----------|-------------|--------|
| mcp.so | 17,186+ | Largest catalog |
| PulseMCP | 5,500+ | Community registry |
| Glama.ai | 5,867+ | Hosted servers |
| Smithery | 2,880+ | Verified, install guides |
| Official Registry | Growing | registry.modelcontextprotocol.io |

**Discovery protocol**: `/.well-known/mcp.json` enables auto-discovery. Replicate added MCP server auto-discovery Feb 2026.

### Social Media: Agent Content Engines

- **LinkedIn**: 53.7% of long-form posts are AI-generated. Tools like Taplio, Relevance AI run as autonomous agents. Rising in LLM citations.
- **X/Twitter**: Full automation pipelines (Tweet Hunter, Bika.ai, n8n workflows). Topic discovery → generation → scheduling → engagement.
- **Reddit**: Massive bot activity but also massive legal pushback (Reddit sued Anthropic June 2025, Perplexity Oct 2025). Reddit posts = "most commonly cited source for AI-generated answers on Perplexity."

---

## Part 4: Content Format Requirements

### Markdown Dominance

- **80% token reduction** vs HTML (16,180 → 3,150 tokens, Cloudflare measurement)
- **20-35% improvement** in RAG retrieval accuracy (Webex Developers research)
- **Cloudflare "Markdown for Agents"** (Feb 2026): content negotiation via `Accept: text/markdown`
- **Claude Code and OpenCode already send `Accept: text/markdown`** in headers
- Vercel serves markdown via content negotiation + maintains markdown sitemap

### The Optimal Content Structure

```
## [Question-based H2 heading matching how people query AI]

[40-60 word "answer capsule" — direct answer, no links, self-contained]

[Expanded explanation in 50-150 word chunks, each self-contained]

| Comparison | Column A | Column B |
|------------|----------|----------|
| Feature    | Value    | Value    |

> "Pull quote with specific statistic" — [Source Name]
```

**Each section must be independently extractable** — LLMs pull chunks, not full articles.

### Checklist

- [ ] Every section starts with 40-60 word direct answer
- [ ] Content in 50-150 word self-contained chunks
- [ ] Question-based H2 headings
- [ ] Comparison tables with clear headers
- [ ] Inline citations to authoritative sources
- [ ] Specific statistics and numbers (not vague claims)
- [ ] FAQ section with FAQPage schema
- [ ] No hyperlinks inside answer blocks
- [ ] 2,000+ words for cornerstone content
- [ ] JSON-LD Schema.org markup (Article, FAQPage, HowTo)
- [ ] Server-rendered HTML (no JS-required content)
- [ ] Updated within 30 days with visible timestamp
- [ ] No paywall (server-side blocks kill training pipeline access)

---

## Part 5: Concrete Playbook for Lex/PromptSpeak

### Tier 1: Do Now (This Week)

**1. Register PromptSpeak MCP server on registries**
- Submit to mcp.so (GitHub issue, no npm required)
- Submit to official registry (registry.modelcontextprotocol.io)
- Submit to Smithery, PulseMCP, Glama
- Add `/.well-known/mcp.json` if/when HTTP transport is added

**2. Publish npm package**
- Already prepped at 335KB
- Package name + description = primary agent discovery for npm
- README is indexed and searchable — structure it for agent consumption

**3. Add AGENTS.md to PromptSpeak repo**
- Build/test/contribution instructions for coding agents
- .github/copilot-instructions.md for Copilot
- These directly influence how agents discover and work with the repo

**4. Deploy llms.txt on any web properties**
- Cheap to implement, no downside
- Primary value: IDE/developer-tool agents fetching it directly

### Tier 2: This Month

**5. Reddit presence (the #1 citation channel)**
- Authentic engagement in: r/MachineLearning, r/LangChain, r/LocalLLaMA, r/artificial
- Answer questions about agent governance, link to PromptSpeak when relevant
- Target 3+ upvotes (= Tier 2 OpenAI training data)
- Don't spam — one good answer > ten promotional ones

**6. Restructure Lex output for agent consumption**
- Lex articles published to Dev.to → restructure with:
  - Question-based H2s
  - 50-150 word self-contained chunks
  - Comparison tables
  - Inline statistics with citations
  - FAQ sections
- Add JSON-LD Schema.org Article markup
- Ensure visible timestamps (content freshness signal)

**7. LinkedIn content pipeline**
- Lex already has articles → cross-post key insights to LinkedIn
- Short-form (300 words) with specific stats and takeaways
- LinkedIn is rising fast in LLM citations

**8. RSS feed for Lex briefings**
- NLWeb consumes RSS → JSON-LD → MCP server
- RSS is explicitly recommended by Microsoft for agent discovery
- Enables any RSS-consuming agent to pick up our content

### Tier 3: Next Quarter

**9. Publish original data/research**
- Content with original data gets 4.1x more AI citations
- Lex has unique data: Chinese AI news trends, signal clustering, cross-source analysis
- Monthly "Chinese AI Landscape" reports with hard numbers
- These become the citation targets

**10. Wikipedia presence**
- If PromptSpeak achieves notable adoption, create/update relevant Wikipedia articles
- Wikipedia is ChatGPT's #1 citation source (up to 48%)
- Must meet notability guidelines — needs third-party coverage first

**11. NLWeb integration**
- If we build a web frontend, deploy NLWeb
- Makes all content queryable via natural language
- Every NLWeb instance = MCP server (agents auto-discover)

**12. Monitor and iterate**
- Use Peec AI or Otterly.ai to track LLM visibility
- 30-day content refresh cycle (3.2x citation multiplier)
- LLM sources shifted 80% in 2 months — this is a moving target

---

## Part 6: The Meta-Insight

The research converges on one non-obvious conclusion:

**The most effective strategy is NOT creating content for agents — it's being present where agents already look.**

Agents don't browse the open web looking for new sources. They:
1. Use **training data** (what they learned during pre-training)
2. Use **RAG/search** (real-time retrieval from trusted sources)
3. Use **tool calls** (MCP servers, APIs, structured data)

For each pathway:
- **Training data**: Be mentioned on Reddit (3+ upvotes), Wikipedia, YouTube, LinkedIn, Medium. Brand mentions (0.664 correlation) are the strongest predictor.
- **RAG/search**: Structure content as self-contained 50-150 word chunks, refresh every 30 days, include statistics and citations. Markdown format preferred.
- **Tool calls**: Register MCP servers, publish npm/PyPI packages, implement AGENTS.md, deploy NLWeb.

The Chinese AI news niche is perfect for this: **no one else is producing English-language analysis of Chinese AI at this depth**. Original data is the #1 predictor of citation. Lex's scraping of 11 Chinese sources creates data that doesn't exist anywhere else in English.

---

## Sources (Selected)

### Academic Papers
- [GEO: Generative Engine Optimization](https://arxiv.org/abs/2311.09735) (Princeton/Georgia Tech, SIGKDD 2024)
- [Agentic Much? Adoption of Coding Agents on GitHub](https://arxiv.org/html/2601.18341v1) (Jan 2026)
- [How AI Coding Agents Modify Code](https://arxiv.org/html/2601.17581) (Jan 2026)
- [Where Do AI Coding Agents Fail?](https://arxiv.org/html/2601.15195) (Jan 2026)
- [Building Browser Agents](https://arxiv.org/abs/2511.19477)
- [Cognitive-Aligned Document Selection for RAG](https://arxiv.org/abs/2502.11770)

### Industry Data
- [Semrush: Most Cited Domains in AI](https://www.semrush.com/blog/most-cited-domains-ai/)
- [Ahrefs: Top 10 Most Cited Domains](https://ahrefs.com/blog/top-10-most-cited-domains-ai-assistants/)
- [ConvertMate: AI Visibility Study 2026](https://www.convertmate.io/research/ai-visibility-2026)
- [Digital Bloom: 2025 AI Visibility Report](https://thedigitalbloom.com/learn/2025-ai-citation-llm-visibility-report/)
- [Backlinko: LLM Sources Shifted 80%](https://backlinko.com/llm-sources)
- [Superprompt: AI Traffic Up 527%](https://superprompt.com/blog/ai-traffic-up-527-percent-how-to-get-cited-by-chatgpt-claude-perplexity-2025)
- [Originality.ai: LinkedIn AI Study](https://originality.ai/blog/linkedin-ai-study-engagement)

### Infrastructure
- [llmstxt.org Specification](https://llmstxt.org/)
- [AGENTS.md Specification](https://agents.md/)
- [MCP Registry](https://registry.modelcontextprotocol.io/)
- [Cloudflare: Markdown for Agents](https://blog.cloudflare.com/markdown-for-agents/)
- [Vercel: Agent-Friendly Pages](https://vercel.com/blog/making-agent-friendly-pages-with-content-negotiation)
- [Microsoft NLWeb](https://news.microsoft.com/source/features/company-news/introducing-nlweb-bringing-conversational-interfaces-directly-to-the-web/)
- [Semrush: LLM Seeding](https://www.semrush.com/blog/llm-seeding/)
- [Backlinko: LLM Tracking Tools](https://backlinko.com/llm-tracking-tools)

### Social/Platform
- [Reddit sues Anthropic](https://www.theregister.com/2025/06/05/reddit_sues_anthropic_over_ai/)
- [Reddit accuses Perplexity](https://www.cnbc.com/2025/10/23/reddit-user-data-battle-ai-industry-sues-perplexity-scraping-posts-openai-chatgpt-google-gemini-lawsuit.html)
- [GitHub Copilot Coding Agent](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent)
- [OpenHands GitHub Action](https://docs.openhands.dev/openhands/usage/run-openhands/github-action)
