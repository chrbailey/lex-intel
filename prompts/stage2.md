Analyze these categorized China tech articles and produce TWO outputs:

1. **MORNING BRIEFING** (300-500 words, Bloomberg style):
   - **LEAD**: Biggest story of the day — why it matters
   - **PATTERNS**: Cross-source themes (if multiple sources report similar trends, highlight them)
   - **SIGNALS**: Emerging trends or early indicators worth watching
   - **WATCHLIST**: Developing stories to track in coming days
   - **DATA**: Key numbers, metrics, funding amounts

2. **POST DRAFTS** for the top 3-5 most notable items, each with:
   - `english_title`: headline
   - `summary`: 1-2 sentence summary
   - `urgency`: "high" | "medium" | "low"
   - `source`: original source name
   - `global_post`: {"text": "LinkedIn/blog post for global audience (200-300 words)"}
   - `china_post`: {"text": "Post for Chinese-market-aware audience (200-300 words, in English)"}

Look for cross-source patterns — if multiple sources report the same theme, that's a signal worth amplifying.

{{HISTORICAL_CONTEXT}}

CATEGORIZED ARTICLES:
{{ARTICLES}}

Return JSON: {"briefing": "markdown text...", "drafts": [{"english_title": "...", "summary": "...", "urgency": "...", "source": "...", "global_post": {"text": "..."}, "china_post": {"text": "..."}}]}
Respond with valid JSON only.
