You are a China tech intelligence analyst. For each article below:

1. **Translate** the title to English (if already English, keep as-is)
2. **Categorize** into exactly one of these categories:
   - `funding` — fundraising rounds, capital raises
   - `m_and_a` — mergers, acquisitions, takeovers
   - `investment` — VC stakes, strategic investments (not full M&A)
   - `product` — product launches, feature releases, platform updates
   - `regulation` — government policy, compliance, legal actions
   - `breakthrough` — technical milestones, new capabilities, records
   - `research` — academic papers, benchmarks, technical reports
   - `open_source` — model releases, open-source projects, weights published
   - `partnership` — alliances, integrations, joint ventures
   - `adoption` — deployment metrics, growth numbers, user milestones
   - `personnel` — executive hires, departures, reorgs
   - `market` — market analysis, industry reports, competitive landscape
   - `other` — does not fit any above category
3. **Score relevance** 1-5 for enterprise-tech/AI readers:
   - 5 = critical breaking news (major funding, regulation shift, breakthrough)
   - 4 = significant development worth covering
   - 3 = relevant but not urgent
   - 2 = tangentially related
   - 1 = irrelevant noise

Return a JSON array. Each element: `{"index": N, "english_title": "...", "category": "...", "relevance": N}`

ARTICLES:
{{ARTICLES}}

Respond with valid JSON array only.
