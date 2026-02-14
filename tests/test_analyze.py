"""Tests for lex analyze module — pure function coverage.

Covers:
  - _parse_claude_json: JSON extraction from markdown, trailing commas, fallback regex
  - _load_prompt: template loading, placeholder substitution, missing file
  - _extract_lead: first non-header paragraph extraction, edge cases
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from lib.analyze import _parse_claude_json, _load_prompt, _extract_lead, PROMPTS_DIR


# ── _parse_claude_json ─────────────────────────────────────


class TestParseClaudeJson:
    """JSON extraction from Claude response text."""

    # ── Happy path ──

    def test_plain_json_object(self):
        assert _parse_claude_json('{"key": "value"}') == {"key": "value"}

    def test_plain_json_array(self):
        result = _parse_claude_json('[{"index": 0, "title": "hi"}]')
        assert isinstance(result, list)
        assert result[0]["index"] == 0

    def test_json_code_block(self):
        text = 'Here is the result:\n```json\n{"a": 1}\n```\nDone.'
        assert _parse_claude_json(text) == {"a": 1}

    def test_json_code_block_array(self):
        text = '```json\n[{"x": 1}, {"x": 2}]\n```'
        result = _parse_claude_json(text)
        assert len(result) == 2
        assert result[1]["x"] == 2

    def test_generic_code_block(self):
        """Non-json code block (``` without json tag) should still extract."""
        text = 'Result:\n```\n{"key": "val"}\n```'
        assert _parse_claude_json(text) == {"key": "val"}

    # ── Trailing commas ──

    def test_trailing_comma_object(self):
        text = '{"a": 1, "b": 2,}'
        result = _parse_claude_json(text)
        assert result == {"a": 1, "b": 2}

    def test_trailing_comma_array(self):
        text = '[1, 2, 3,]'
        result = _parse_claude_json(text)
        assert result == [1, 2, 3]

    def test_trailing_comma_nested(self):
        text = '{"items": [1, 2,], "name": "test",}'
        result = _parse_claude_json(text)
        assert result["items"] == [1, 2]
        assert result["name"] == "test"

    def test_multiple_trailing_commas(self):
        text = '{"a": {"b": 1,}, "c": [3,],}'
        result = _parse_claude_json(text)
        assert result["a"]["b"] == 1
        assert result["c"] == [3]

    # ── Nested objects ──

    def test_deeply_nested(self):
        obj = {"level1": {"level2": {"level3": "deep"}}}
        text = json.dumps(obj)
        assert _parse_claude_json(text) == obj

    def test_nested_in_code_block(self):
        obj = {"briefing": "text", "drafts": [{"title": "A", "post": {"text": "B"}}]}
        text = f"```json\n{json.dumps(obj)}\n```"
        assert _parse_claude_json(text) == obj

    # ── Fallback regex extraction ──

    def test_json_embedded_in_prose(self):
        """When there are no code blocks, regex should find the JSON object."""
        text = 'Here is your data: {"result": 42} and that is all.'
        assert _parse_claude_json(text) == {"result": 42}

    def test_json_object_with_leading_text(self):
        text = 'Sure, here you go:\n\n{"key": "value"}'
        assert _parse_claude_json(text) == {"key": "value"}

    # ── Malformed / edge cases ──

    def test_empty_string(self):
        assert _parse_claude_json("") is None

    def test_whitespace_only(self):
        assert _parse_claude_json("   \n\t  ") is None

    def test_completely_invalid(self):
        assert _parse_claude_json("this is not json at all") is None

    def test_partial_json(self):
        """Truncated JSON should return None."""
        assert _parse_claude_json('{"key": "val') is None

    def test_empty_code_block(self):
        text = "```json\n\n```"
        assert _parse_claude_json(text) is None

    def test_code_block_with_only_text(self):
        text = "```json\nnot json content\n```"
        assert _parse_claude_json(text) is None

    def test_multiple_code_blocks_takes_first_json(self):
        text = '```json\n{"first": true}\n```\nAnd also:\n```json\n{"second": true}\n```'
        result = _parse_claude_json(text)
        assert result == {"first": True}

    # ── Types ──

    def test_returns_int(self):
        assert _parse_claude_json("42") == 42

    def test_returns_string(self):
        assert _parse_claude_json('"hello"') == "hello"

    def test_returns_null(self):
        assert _parse_claude_json("null") is None

    def test_returns_bool(self):
        assert _parse_claude_json("true") is True

    # ── Realistic Claude output ──

    def test_stage1_shaped_response(self):
        """Realistic Stage 1 output."""
        text = '```json\n[\n  {"index": 0, "english_title": "ByteDance raises $2B", "category": "funding", "relevance": 5},\n  {"index": 1, "english_title": "New AI chip released", "category": "product", "relevance": 4}\n]\n```'
        result = _parse_claude_json(text)
        assert len(result) == 2
        assert result[0]["category"] == "funding"
        assert result[1]["relevance"] == 4

    def test_stage2_shaped_response(self):
        """Realistic Stage 2 output."""
        obj = {
            "briefing": "# LEAD\nBig news today.\n\n# PATTERNS\nTrend spotted.",
            "drafts": [
                {
                    "english_title": "Test Article",
                    "summary": "Summary here",
                    "urgency": "high",
                    "source": "36kr",
                    "global_post": {"text": "Global post text"},
                    "china_post": {"text": "China post text"},
                }
            ],
        }
        text = f"```json\n{json.dumps(obj, indent=2)}\n```"
        result = _parse_claude_json(text)
        assert result["briefing"].startswith("# LEAD")
        assert len(result["drafts"]) == 1
        assert result["drafts"][0]["urgency"] == "high"

    def test_unicode_content(self):
        text = '{"title": "\u5b57\u8282\u8df3\u52a8\u878d\u8d44\u4e24\u5341\u4ebf"}'
        result = _parse_claude_json(text)
        assert result["title"] == "\u5b57\u8282\u8df3\u52a8\u878d\u8d44\u4e24\u5341\u4ebf"


# ── _load_prompt ───────────────────────────────────────────


class TestLoadPrompt:
    """Template loading from prompts/ directory."""

    # ── Real prompts directory ──

    def test_load_stage1(self):
        """stage1.md should load and contain the ARTICLES placeholder."""
        result = _load_prompt("stage1", ARTICLES="test data")
        assert "test data" in result
        assert "{{ARTICLES}}" not in result

    def test_load_stage2(self):
        """stage2.md should load and substitute both placeholders."""
        result = _load_prompt(
            "stage2",
            ARTICLES="categorized data",
            HISTORICAL_CONTEXT="past context",
        )
        assert "categorized data" in result
        assert "past context" in result
        assert "{{ARTICLES}}" not in result
        assert "{{HISTORICAL_CONTEXT}}" not in result

    def test_stage1_has_category_list(self):
        """stage1 template should list the 13 categories."""
        result = _load_prompt("stage1", ARTICLES="")
        for cat in ["funding", "m_and_a", "regulation", "breakthrough", "open_source"]:
            assert cat in result

    def test_stage2_has_briefing_sections(self):
        """stage2 template should reference LEAD/PATTERNS/SIGNALS."""
        result = _load_prompt("stage2", ARTICLES="", HISTORICAL_CONTEXT="")
        for section in ["LEAD", "PATTERNS", "SIGNALS", "WATCHLIST", "DATA"]:
            assert section in result

    # ── Missing file ──

    def test_missing_template_raises(self):
        with pytest.raises(FileNotFoundError, match="Prompt template not found"):
            _load_prompt("nonexistent_template_xyz")

    # ── Placeholder substitution ──

    def test_placeholder_case_insensitive_key(self):
        """kwargs keys are uppercased before substitution."""
        result = _load_prompt("stage1", articles="my articles")
        assert "my articles" in result
        assert "{{ARTICLES}}" not in result

    def test_unused_placeholder_remains(self):
        """If a placeholder isn't provided, it stays in the text."""
        result = _load_prompt("stage2", ARTICLES="data")
        # HISTORICAL_CONTEXT was not provided, so the placeholder remains
        assert "{{HISTORICAL_CONTEXT}}" in result

    def test_empty_substitution(self):
        """Empty string substitution should work."""
        result = _load_prompt("stage1", ARTICLES="")
        assert "{{ARTICLES}}" not in result

    # ── tmp_path based tests for isolated behavior ──

    def test_load_custom_template(self, tmp_path):
        """Test with a synthetic template using patched PROMPTS_DIR."""
        template = tmp_path / "custom.md"
        template.write_text("Hello {{NAME}}, you have {{COUNT}} items.", encoding="utf-8")

        with patch("lib.analyze.PROMPTS_DIR", tmp_path):
            result = _load_prompt("custom", NAME="Alice", COUNT="5")
        assert result == "Hello Alice, you have 5 items."

    def test_numeric_value_substitution(self, tmp_path):
        """Non-string values should be converted via str()."""
        template = tmp_path / "nums.md"
        template.write_text("Score: {{SCORE}}", encoding="utf-8")

        with patch("lib.analyze.PROMPTS_DIR", tmp_path):
            result = _load_prompt("nums", SCORE=42)
        assert result == "Score: 42"

    def test_multiline_template(self, tmp_path):
        template = tmp_path / "multi.md"
        template.write_text("Line 1\n{{CONTENT}}\nLine 3", encoding="utf-8")

        with patch("lib.analyze.PROMPTS_DIR", tmp_path):
            result = _load_prompt("multi", CONTENT="Line 2")
        assert result == "Line 1\nLine 2\nLine 3"

    def test_no_kwargs_returns_raw(self, tmp_path):
        """Calling without kwargs returns the template as-is."""
        template = tmp_path / "raw.md"
        template.write_text("No placeholders here.", encoding="utf-8")

        with patch("lib.analyze.PROMPTS_DIR", tmp_path):
            result = _load_prompt("raw")
        assert result == "No placeholders here."

    def test_repeated_placeholder(self, tmp_path):
        """Same placeholder used multiple times should all be replaced."""
        template = tmp_path / "repeat.md"
        template.write_text("{{NAME}} likes {{NAME}}", encoding="utf-8")

        with patch("lib.analyze.PROMPTS_DIR", tmp_path):
            result = _load_prompt("repeat", NAME="Bob")
        assert result == "Bob likes Bob"

    def test_missing_file_in_tmp_dir(self, tmp_path):
        with patch("lib.analyze.PROMPTS_DIR", tmp_path):
            with pytest.raises(FileNotFoundError):
                _load_prompt("does_not_exist")


# ── _extract_lead ──────────────────────────────────────────


class TestExtractLead:
    """First non-header paragraph extraction from briefing text."""

    # ── Normal cases ──

    def test_simple_paragraph(self):
        text = "This is the lead paragraph."
        assert _extract_lead(text) == "This is the lead paragraph."

    def test_paragraph_after_header(self):
        text = "# LEAD\n\nThis is the actual lead content."
        assert _extract_lead(text) == "This is the actual lead content."

    def test_multiple_headers_before_content(self):
        text = "# LEAD\n\n## Sub-header\n\nActual content here."
        assert _extract_lead(text) == "Actual content here."

    def test_skips_all_header_levels(self):
        text = "# H1\n\n## H2\n\n### H3\n\nFinally content."
        assert _extract_lead(text) == "Finally content."

    def test_takes_first_non_header_paragraph(self):
        text = "# LEAD\n\nFirst paragraph.\n\nSecond paragraph."
        assert _extract_lead(text) == "First paragraph."

    def test_multiline_paragraph(self):
        text = "# Title\n\nLine one\nline two\nline three."
        assert _extract_lead(text) == "Line one\nline two\nline three."

    # ── Truncation ──

    def test_truncates_at_500_chars(self):
        long_text = "A" * 600
        result = _extract_lead(long_text)
        assert len(result) == 500

    def test_truncation_with_header(self):
        text = "# Header\n\n" + "B" * 600
        result = _extract_lead(text)
        assert len(result) == 500
        assert result == "B" * 500

    # ── Fallback to first 500 chars ──

    def test_header_only_falls_back(self):
        """If every section starts with #, fall back to first 500 chars."""
        text = "# Header One\n\n# Header Two\n\n# Header Three"
        result = _extract_lead(text)
        assert result == text[:500]

    # ── Empty / None input ──

    def test_empty_string(self):
        assert _extract_lead("") is None

    def test_none_input(self):
        assert _extract_lead(None) is None

    def test_whitespace_only(self):
        """Whitespace-only sections are stripped; fallback applies."""
        text = "   \n\n   \n\n   "
        result = _extract_lead(text)
        # All sections strip to empty, so fallback: text[:500]
        assert result == text[:500]

    # ── Realistic briefing text ──

    def test_realistic_briefing(self):
        text = (
            "# LEAD\n\n"
            "ByteDance secured $2B in funding, marking the largest AI raise this quarter.\n\n"
            "# PATTERNS\n\n"
            "Multiple sources report accelerating enterprise AI adoption.\n\n"
            "# SIGNALS\n\n"
            "Early indicators of regulatory tightening in the EU."
        )
        result = _extract_lead(text)
        assert result.startswith("ByteDance secured $2B")
        assert "PATTERNS" not in result

    def test_no_headers_returns_first_paragraph(self):
        text = "First paragraph here.\n\nSecond paragraph there."
        assert _extract_lead(text) == "First paragraph here."

    def test_content_starts_immediately(self):
        """No header, no blank line — content is the first section."""
        text = "Breaking news today."
        assert _extract_lead(text) == "Breaking news today."

    def test_header_with_no_following_content(self):
        """Header followed by nothing."""
        text = "# LEAD"
        result = _extract_lead(text)
        # Single section, starts with #, so fallback
        assert result == text[:500]

    def test_empty_paragraphs_between_headers(self):
        """Empty paragraphs (just whitespace) between headers should be skipped."""
        text = "# H1\n\n\n\n# H2\n\nContent here."
        result = _extract_lead(text)
        assert result == "Content here."
