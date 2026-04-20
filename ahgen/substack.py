"""
Beijing to Breakfast — Substack Newsletter Formatter

Takes raw briefing output from the Lex/Ahgen pipeline and formats it
as a Substack-ready newsletter with the B2B structure:
LEAD / PATTERNS / SIGNALS / WATCHLIST / DATA

Outputs both markdown (for file storage) and HTML (for email/Substack).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("ahgen.substack")

# Section headers expected from the stage2 briefing output
_SECTION_ORDER = ["LEAD", "PATTERNS", "SIGNALS", "WATCHLIST", "DATA"]

_FOOTER_MD = (
    "*Beijing to Breakfast is a daily briefing by Christopher Bailey, "
    "powered by [Lex Intel](https://github.com/chrbailey/lex-intel). "
    "Scraping 11 Chinese-language tech outlets overnight, analyzed and "
    "delivered before your first coffee.*"
)

_FOOTER_HTML = (
    '<p style="color: #888; font-size: 13px; font-style: italic; '
    'margin-top: 32px; border-top: 1px solid #ddd; padding-top: 12px;">'
    "Beijing to Breakfast is a daily briefing by Christopher Bailey, "
    'powered by <a href="https://github.com/chrbailey/lex-intel" '
    'style="color: #888;">Lex Intel</a>. '
    "Scraping 11 Chinese-language tech outlets overnight, analyzed and "
    "delivered before your first coffee.</p>"
)


def _extract_sections(briefing: str) -> Dict[str, str]:
    """Parse the stage2 briefing text into named sections.

    The briefing from stage2_pattern_analysis uses headers like:
    LEAD, PATTERNS, SIGNALS, WATCHLIST, DATA (with optional ## prefix).
    """
    sections = {}  # type: Dict[str, str]

    if not briefing:
        return sections

    # Normalize heading markers so we can split reliably
    # Handles: ## LEAD, **LEAD**, LEAD:, ### LEAD, etc.
    pattern = re.compile(
        r"(?:^|\n)\s*(?:#{1,4}\s*)?(?:\*{1,2})?\s*("
        + "|".join(_SECTION_ORDER)
        + r")\s*(?:\*{1,2})?[\s:—\-]*\n",
        re.IGNORECASE,
    )

    # Find all section boundaries
    matches = list(pattern.finditer(briefing))

    if not matches:
        # No recognizable sections — treat entire briefing as LEAD
        sections["LEAD"] = briefing.strip()
        return sections

    for i, m in enumerate(matches):
        name = m.group(1).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(briefing)
        body = briefing[start:end].strip()
        if body:
            sections[name] = body

    # If there's content before the first matched section, prepend to LEAD
    preamble = briefing[: matches[0].start()].strip()
    if preamble:
        existing_lead = sections.get("LEAD", "")
        sections["LEAD"] = (preamble + "\n\n" + existing_lead).strip()

    return sections


def _sections_to_markdown(sections: Dict[str, str], date_str: str) -> str:
    """Assemble sections into the B2B markdown format."""
    lines = [
        f"# Beijing to Breakfast — {date_str}",
        "*Overnight intelligence from China's AI ecosystem*",
        "",
        "---",
        "",
    ]

    for name in _SECTION_ORDER:
        body = sections.get(name)
        if body:
            lines.append(f"## {name}")
            lines.append(body)
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(_FOOTER_MD)
    lines.append("")

    return "\n".join(lines)


def _md_to_html_simple(text: str) -> str:
    """Minimal markdown-to-HTML conversion for newsletter content.

    Handles: paragraphs, bold, italic, links, bullet lists.
    Not a full parser — just enough for clean Substack rendering.
    """
    html_parts = []  # type: List[str]

    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue

        # Bullet lists
        if block.startswith("- ") or block.startswith("* "):
            items = []
            for line in block.split("\n"):
                line = line.strip()
                if line.startswith("- ") or line.startswith("* "):
                    items.append("<li>{}</li>".format(line[2:]))
                elif items:
                    # Continuation line
                    items[-1] = items[-1].replace("</li>", " " + line + "</li>")
            html_parts.append("<ul>{}</ul>".format("".join(items)))
            continue

        # Single-line that looks like a sub-heading within a section
        if block.startswith("### "):
            html_parts.append("<h4>{}</h4>".format(block[4:]))
            continue

        # Default: paragraph
        html_parts.append("<p>{}</p>".format(block))

    result = "\n".join(html_parts)

    # Inline formatting
    result = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", result)
    result = re.sub(r"\*(.+?)\*", r"<em>\1</em>", result)
    result = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" style="color: #1a73e8;">\1</a>',
        result,
    )

    return result


def _sections_to_html(sections: Dict[str, str], date_str: str) -> str:
    """Assemble sections into the B2B HTML email/Substack format."""
    parts = [
        '<html><body style="font-family: Georgia, \'Times New Roman\', serif; '
        'max-width: 640px; margin: 0 auto; padding: 20px; color: #1a1a1a;">',
        '<h1 style="font-size: 28px; margin-bottom: 4px;">Beijing to Breakfast</h1>',
        '<p style="color: #666; font-size: 15px; margin-top: 0;">{}</p>'.format(
            date_str
        ),
        '<p style="color: #888; font-size: 14px; font-style: italic; '
        'margin-bottom: 24px;">Overnight intelligence from China\'s AI ecosystem</p>',
        '<hr style="border: none; border-top: 2px solid #222; margin: 16px 0;">',
    ]

    section_colors = {
        "LEAD": "#c0392b",
        "PATTERNS": "#2980b9",
        "SIGNALS": "#8e44ad",
        "WATCHLIST": "#d35400",
        "DATA": "#27ae60",
    }

    for name in _SECTION_ORDER:
        body = sections.get(name)
        if not body:
            continue

        color = section_colors.get(name, "#333")
        parts.append(
            '<h2 style="font-size: 20px; color: {}; margin-top: 28px; '
            'margin-bottom: 8px; letter-spacing: 1px;">{}</h2>'.format(color, name)
        )
        parts.append(
            '<div style="margin-bottom: 20px; line-height: 1.6;">'
        )
        parts.append(_md_to_html_simple(body))
        parts.append("</div>")

    parts.append('<hr style="border: none; border-top: 2px solid #222; margin: 24px 0;">')
    parts.append(_FOOTER_HTML)
    parts.append("</body></html>")

    return "\n".join(parts)


def format_b2b_newsletter(
    briefing: str,
    drafts: List[Dict],
    date: str,
) -> Tuple[str, str]:
    """Format pipeline output as a Beijing to Breakfast newsletter.

    Args:
        briefing: Raw briefing text from stage2_pattern_analysis().
        drafts: List of draft dicts from the pipeline (used for supplementary data).
        date: Date string for the newsletter header (e.g. "2026-04-07").

    Returns:
        Tuple of (markdown, html) newsletter content.
    """
    # Parse briefing into sections
    sections = _extract_sections(briefing)

    # If drafts contain structured data not in the briefing, fold it in
    if drafts and "DATA" not in sections:
        data_lines = []
        for draft in drafts:
            summary = draft.get("summary", "")
            urgency = draft.get("urgency", "")
            source = draft.get("source", "")
            if summary:
                marker = "[{}]".format(urgency.upper()) if urgency else ""
                data_lines.append(
                    "- {} {} (via {})".format(marker, summary, source)
                )
        if data_lines:
            sections["DATA"] = "\n".join(data_lines)

    # If drafts have watchlist-worthy items and no WATCHLIST section exists
    if drafts and "WATCHLIST" not in sections:
        companies = []  # type: List[str]
        for draft in drafts:
            src = draft.get("source", "")
            summary = draft.get("summary", "")
            if src and summary:
                companies.append("- **{}**: {}".format(src, summary))
        if companies:
            sections["WATCHLIST"] = "\n".join(companies)

    if not sections:
        log.warning("No content to format for B2B newsletter")
        empty_md = "# Beijing to Breakfast — {}\n\nNo intelligence collected overnight.\n".format(date)
        empty_html = (
            "<html><body><h1>Beijing to Breakfast</h1>"
            "<p>No intelligence collected overnight.</p></body></html>"
        )
        return empty_md, empty_html

    md = _sections_to_markdown(sections, date)
    html = _sections_to_html(sections, date)

    log.info(
        "B2B newsletter formatted: %d sections, %d chars md, %d chars html",
        len(sections),
        len(md),
        len(html),
    )

    return md, html
