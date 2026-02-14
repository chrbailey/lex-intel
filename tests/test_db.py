"""Tests for lex/lib/db.py — pure functions and mocked Supabase calls."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from lib.db import _normalize_title, _parse_date, _source_id


# ── _normalize_title ────────────────────────────────────────


class TestNormalizeTitle:
    """Tests for _normalize_title: Unicode normalization, lowercasing,
    punctuation removal, whitespace collapse."""

    def test_basic_lowercase(self):
        assert _normalize_title("Hello World") == "hello world"

    def test_removes_punctuation(self):
        assert _normalize_title("Hello, World!") == "hello world"

    def test_collapses_whitespace(self):
        assert _normalize_title("hello   world") == "hello world"

    def test_strips_leading_trailing_whitespace(self):
        assert _normalize_title("  hello world  ") == "hello world"

    def test_empty_string(self):
        assert _normalize_title("") == ""

    def test_only_whitespace(self):
        assert _normalize_title("   ") == ""

    def test_only_punctuation(self):
        assert _normalize_title("!@#$%^&*()") == ""

    def test_unicode_chinese_characters(self):
        result = _normalize_title("DeepSeek发布新模型")
        assert "deepseek" in result
        # Chinese characters are \w in Python regex, so they survive
        assert "\u53d1\u5e03" in result  # 发布

    def test_unicode_nfkc_normalization(self):
        # NFKC normalizes fullwidth Latin letters to ASCII
        fullwidth_a = "\uff21"  # Fullwidth A
        result = _normalize_title(fullwidth_a)
        assert result == "a"

    def test_mixed_chinese_english(self):
        result = _normalize_title("AI新闻: DeepSeek-V3 Released!")
        assert result == "ai\u65b0\u95fb deepseekv3 released"

    def test_tabs_and_newlines_collapsed(self):
        assert _normalize_title("hello\t\tworld\n\nfoo") == "hello world foo"

    def test_hyphens_removed(self):
        # Hyphens are punctuation, so they get removed
        assert _normalize_title("state-of-the-art") == "stateoftheart"

    def test_numbers_preserved(self):
        assert _normalize_title("GPT-4o 2024") == "gpt4o 2024"

    def test_underscores_preserved(self):
        # Underscores are \w, so they survive the regex
        assert _normalize_title("hello_world") == "hello_world"

    def test_accented_characters(self):
        # NFKC preserves composed accented characters
        result = _normalize_title("Cafe\u0301")
        assert result == "caf\u00e9"

    def test_idempotent(self):
        """Normalizing an already-normalized string should not change it."""
        original = "deepseek releases v3 model"
        assert _normalize_title(_normalize_title(original)) == original

    def test_emoji_removed(self):
        # Emojis are not \w or \s, so they get stripped
        result = _normalize_title("AI News \U0001f525\U0001f680")
        assert result == "ai news"

    def test_curly_quotes_removed(self):
        result = _normalize_title("\u201cHello\u201d \u2018World\u2019")
        assert result == "hello world"

    def test_ellipsis_removed(self):
        result = _normalize_title("Breaking news\u2026 more details")
        assert result == "breaking news more details"


# ── _parse_date ─────────────────────────────────────────────


class TestParseDate:
    """Tests for _parse_date: RFC 2822, ISO 8601, None handling, (UTC) suffix."""

    def test_none_returns_none(self):
        assert _parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_date("") is None

    def test_whitespace_only_returns_none(self):
        assert _parse_date("   ") is None

    def test_rfc_2822_date(self):
        raw = "Sat, 14 Feb 2026 07:50:00 +0000"
        result = _parse_date(raw)
        assert result is not None
        dt = datetime.fromisoformat(result)
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 14

    def test_rfc_2822_with_timezone_offset(self):
        raw = "Mon, 10 Feb 2026 15:30:00 -0500"
        result = _parse_date(raw)
        assert result is not None
        dt = datetime.fromisoformat(result)
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 10

    def test_iso_8601_basic(self):
        raw = "2026-02-14T07:50:00+00:00"
        result = _parse_date(raw)
        assert result is not None
        dt = datetime.fromisoformat(result)
        assert dt.year == 2026

    def test_iso_8601_with_z_suffix(self):
        raw = "2026-02-14T07:50:00Z"
        result = _parse_date(raw)
        assert result is not None
        dt = datetime.fromisoformat(result)
        assert dt.year == 2026
        assert dt.month == 2

    def test_iso_8601_date_only(self):
        raw = "2026-02-14"
        result = _parse_date(raw)
        assert result is not None

    def test_utc_suffix_stripped(self):
        raw = "2026-02-14T07:50:00+00:00 (UTC)"
        result = _parse_date(raw)
        assert result is not None
        dt = datetime.fromisoformat(result)
        assert dt.year == 2026

    def test_utc_suffix_with_rfc_2822(self):
        raw = "Sat, 14 Feb 2026 07:50:00 +0000 (UTC)"
        result = _parse_date(raw)
        assert result is not None
        dt = datetime.fromisoformat(result)
        assert dt.year == 2026

    def test_completely_garbage_returns_none(self):
        assert _parse_date("not a date at all") is None

    def test_partial_date_returns_none(self):
        assert _parse_date("Feb 2026") is None

    def test_leading_trailing_whitespace_stripped(self):
        raw = "  2026-02-14T07:50:00Z  "
        result = _parse_date(raw)
        assert result is not None

    def test_iso_result_is_parseable(self):
        """Output should itself be valid ISO 8601."""
        raw = "Sat, 14 Feb 2026 07:50:00 +0000"
        result = _parse_date(raw)
        # Should not raise
        dt = datetime.fromisoformat(result)
        assert isinstance(dt, datetime)

    def test_iso_with_microseconds(self):
        raw = "2026-02-14T07:50:00.123456+00:00"
        result = _parse_date(raw)
        assert result is not None
        dt = datetime.fromisoformat(result)
        assert dt.microsecond == 123456

    def test_negative_timezone(self):
        raw = "2026-02-14T07:50:00-08:00"
        result = _parse_date(raw)
        assert result is not None
        dt = datetime.fromisoformat(result)
        assert dt.hour == 7

    def test_chinese_date_format_returns_none(self):
        # Chinese date strings without standard format should fail gracefully
        assert _parse_date("\u4e8c\u96f6\u4e8c\u516d\u5e74\u4e8c\u6708") is None


# ── _source_id ──────────────────────────────────────────────


class TestSourceId:
    """Tests for _source_id: SHA256 hash, deterministic, 16-char."""

    def test_returns_16_chars(self):
        result = _source_id("techcrunch", "AI News Today")
        assert len(result) == 16

    def test_hex_characters_only(self):
        result = _source_id("source", "title")
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        a = _source_id("src", "title", "http://example.com")
        b = _source_id("src", "title", "http://example.com")
        assert a == b

    def test_different_sources_different_ids(self):
        a = _source_id("techcrunch", "AI News")
        b = _source_id("reuters", "AI News")
        assert a != b

    def test_different_titles_different_ids(self):
        a = _source_id("src", "Title A")
        b = _source_id("src", "Title B")
        assert a != b

    def test_url_takes_precedence_over_title(self):
        """When url is provided, it's used instead of title in the hash."""
        with_url = _source_id("src", "Title", "http://example.com/article")
        without_url = _source_id("src", "Title")
        assert with_url != without_url

    def test_url_none_uses_title(self):
        result = _source_id("src", "My Title", None)
        expected_key = "src:My Title"
        expected = hashlib.sha256(expected_key.encode()).hexdigest()[:16]
        assert result == expected

    def test_url_provided_uses_url(self):
        result = _source_id("src", "Title", "http://example.com")
        expected_key = "src:http://example.com"
        expected = hashlib.sha256(expected_key.encode()).hexdigest()[:16]
        assert result == expected

    def test_chinese_title(self):
        result = _source_id("36kr", "\u6df1\u5ea6\u5b66\u4e60\u65b0\u7a81\u7834")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_source_and_title(self):
        result = _source_id("", "")
        assert len(result) == 16
        expected_key = ":"
        expected = hashlib.sha256(expected_key.encode()).hexdigest()[:16]
        assert result == expected

    def test_special_characters_in_title(self):
        result = _source_id("src", "Title: With! Special@#$% Chars")
        assert len(result) == 16

    def test_url_default_parameter(self):
        """Calling without url arg should use title."""
        result = _source_id("src", "My Title")
        expected_key = "src:My Title"
        expected = hashlib.sha256(expected_key.encode()).hexdigest()[:16]
        assert result == expected


# ── is_duplicate (mocked Supabase) ──────────────────────────


class TestIsDuplicate:
    """Tests for is_duplicate with mocked Supabase client."""

    def _mock_client(self, query_data):
        """Create a mock Supabase client that returns query_data from a select chain."""
        client = MagicMock()
        execute_result = MagicMock()
        execute_result.data = query_data

        table = client.table.return_value
        select = table.select.return_value
        eq = select.eq.return_value
        gte = eq.gte.return_value
        limit = gte.limit.return_value
        limit.execute.return_value = execute_result

        return client

    @patch("lib.db._get_client")
    def test_empty_title_returns_true(self, mock_get_client):
        """Empty or whitespace-only titles are considered duplicates."""
        from lib.db import is_duplicate
        assert is_duplicate("") is True
        assert is_duplicate("   ") is True
        assert is_duplicate("!@#$%") is True  # normalizes to empty
        # Should NOT call Supabase for empty titles
        mock_get_client.assert_not_called()

    @patch("lib.db._get_client")
    def test_exact_match_found(self, mock_get_client):
        """When a matching title exists in dedup_titles, return True."""
        from lib.db import is_duplicate
        mock_get_client.return_value = self._mock_client([{"id": "abc123"}])
        assert is_duplicate("AI News Today") is True

    @patch("lib.db._get_client")
    def test_no_match_found(self, mock_get_client):
        """When no matching title exists, return False."""
        from lib.db import is_duplicate
        mock_get_client.return_value = self._mock_client([])
        assert is_duplicate("Unique Article Title") is False

    @patch("lib.db._get_client")
    def test_normalizes_before_query(self, mock_get_client):
        """Title should be normalized before querying."""
        from lib.db import is_duplicate
        client = self._mock_client([])
        mock_get_client.return_value = client

        is_duplicate("  Hello, World!  ")

        # The eq call should use the normalized title
        table = client.table.return_value
        select = table.select.return_value
        select.eq.assert_called_once_with("title_norm", "hello world")

    @patch("lib.db._get_client")
    def test_queries_dedup_titles_table(self, mock_get_client):
        """Should query the dedup_titles table."""
        from lib.db import is_duplicate
        client = self._mock_client([])
        mock_get_client.return_value = client

        is_duplicate("Some Title")

        client.table.assert_called_once_with("dedup_titles")

    @patch("lib.db._get_client")
    def test_chinese_title_duplicate_check(self, mock_get_client):
        """Chinese titles should be normalized and checked."""
        from lib.db import is_duplicate
        client = self._mock_client([{"id": "match"}])
        mock_get_client.return_value = client

        result = is_duplicate("\u6df1\u5ea6\u5b66\u4e60\u65b0\u7a81\u7834")
        assert result is True

    @patch("lib.db._get_client")
    def test_uses_30_day_window(self, mock_get_client):
        """Should filter by seen_at >= 30 days ago."""
        from lib.db import is_duplicate
        client = self._mock_client([])
        mock_get_client.return_value = client

        is_duplicate("Test Title")

        table = client.table.return_value
        select = table.select.return_value
        eq = select.eq.return_value
        # gte should be called with "seen_at" and an ISO date string
        args = eq.gte.call_args
        assert args[0][0] == "seen_at"
        # The cutoff should be roughly 30 days ago
        cutoff_str = args[0][1]
        cutoff = datetime.fromisoformat(cutoff_str)
        now = datetime.now(timezone.utc)
        diff = now - cutoff
        assert 29 <= diff.days <= 31


# ── cleanup_dedup (mocked Supabase) ─────────────────────────


class TestCleanupDedup:
    """Tests for cleanup_dedup with mocked Supabase client."""

    def _mock_client(self, deleted_data):
        """Create a mock Supabase client for delete operations."""
        client = MagicMock()
        execute_result = MagicMock()
        execute_result.data = deleted_data

        table = client.table.return_value
        delete = table.delete.return_value
        lt = delete.lt.return_value
        lt.execute.return_value = execute_result

        return client

    @patch("lib.db._get_client")
    def test_returns_count_of_deleted_rows(self, mock_get_client):
        from lib.db import cleanup_dedup
        mock_get_client.return_value = self._mock_client(
            [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        )
        assert cleanup_dedup() == 3

    @patch("lib.db._get_client")
    def test_returns_zero_when_nothing_deleted(self, mock_get_client):
        from lib.db import cleanup_dedup
        mock_get_client.return_value = self._mock_client([])
        assert cleanup_dedup() == 0

    @patch("lib.db._get_client")
    def test_uses_correct_table(self, mock_get_client):
        from lib.db import cleanup_dedup
        client = self._mock_client([])
        mock_get_client.return_value = client

        cleanup_dedup()

        client.table.assert_called_once_with("dedup_titles")

    @patch("lib.db._get_client")
    def test_custom_days_parameter(self, mock_get_client):
        from lib.db import cleanup_dedup
        client = self._mock_client([])
        mock_get_client.return_value = client

        cleanup_dedup(days=7)

        table = client.table.return_value
        delete = table.delete.return_value
        args = delete.lt.call_args
        assert args[0][0] == "seen_at"
        cutoff_str = args[0][1]
        cutoff = datetime.fromisoformat(cutoff_str)
        now = datetime.now(timezone.utc)
        diff = now - cutoff
        assert 6 <= diff.days <= 8

    @patch("lib.db._get_client")
    def test_default_30_day_cutoff(self, mock_get_client):
        from lib.db import cleanup_dedup
        client = self._mock_client([])
        mock_get_client.return_value = client

        cleanup_dedup()

        table = client.table.return_value
        delete = table.delete.return_value
        args = delete.lt.call_args
        cutoff_str = args[0][1]
        cutoff = datetime.fromisoformat(cutoff_str)
        now = datetime.now(timezone.utc)
        diff = now - cutoff
        assert 29 <= diff.days <= 31


# ── get_analytics (mocked Supabase) ─────────────────────────


class TestGetAnalytics:
    """Tests for get_analytics with mocked Supabase client."""

    def _build_mock_client(self, articles_data, publish_data, briefings_data, briefings_count):
        """Build a mock client that handles three separate table() calls."""
        client = MagicMock()

        # We need table() to return different mocks for different table names
        table_mocks = {}

        # -- articles table --
        articles_mock = MagicMock()
        articles_exec = MagicMock()
        articles_exec.data = articles_data
        articles_select = articles_mock.select.return_value
        articles_gte = articles_select.gte.return_value
        articles_gte.execute.return_value = articles_exec
        table_mocks["articles"] = articles_mock

        # -- publish_queue table --
        pub_mock = MagicMock()
        pub_exec = MagicMock()
        pub_exec.data = publish_data
        pub_select = pub_mock.select.return_value
        pub_gte = pub_select.gte.return_value
        pub_gte.execute.return_value = pub_exec
        table_mocks["publish_queue"] = pub_mock

        # -- briefings table --
        briefings_mock = MagicMock()
        briefings_exec = MagicMock()
        briefings_exec.data = briefings_data
        briefings_exec.count = briefings_count
        briefings_select = briefings_mock.select.return_value
        briefings_gte = briefings_select.gte.return_value
        briefings_gte.execute.return_value = briefings_exec
        table_mocks["briefings"] = briefings_mock

        def table_side_effect(name):
            return table_mocks.get(name, MagicMock())

        client.table.side_effect = table_side_effect

        return client

    @patch("lib.db._get_client")
    def test_returns_correct_structure(self, mock_get_client):
        from lib.db import get_analytics
        mock_get_client.return_value = self._build_mock_client([], [], [], 0)

        result = get_analytics()

        assert "days" in result
        assert "articles_total" in result
        assert "source_quality" in result
        assert "category_distribution" in result
        assert "publish_stats" in result
        assert "briefings" in result
        assert "total" in result["briefings"]
        assert "emailed" in result["briefings"]

    @patch("lib.db._get_client")
    def test_default_days(self, mock_get_client):
        from lib.db import get_analytics
        mock_get_client.return_value = self._build_mock_client([], [], [], 0)

        result = get_analytics()
        assert result["days"] == 30

    @patch("lib.db._get_client")
    def test_custom_days(self, mock_get_client):
        from lib.db import get_analytics
        mock_get_client.return_value = self._build_mock_client([], [], [], 0)

        result = get_analytics(days=7)
        assert result["days"] == 7

    @patch("lib.db._get_client")
    def test_empty_data_returns_zeros(self, mock_get_client):
        from lib.db import get_analytics
        mock_get_client.return_value = self._build_mock_client([], [], [], 0)

        result = get_analytics()

        assert result["articles_total"] == 0
        assert result["source_quality"] == {}
        assert result["category_distribution"] == {}
        assert result["publish_stats"] == {}
        assert result["briefings"]["total"] == 0
        assert result["briefings"]["emailed"] == 0

    @patch("lib.db._get_client")
    def test_source_quality_calculation(self, mock_get_client):
        from lib.db import get_analytics
        articles = [
            {"source": "techcrunch", "category": "ai", "relevance": 5},
            {"source": "techcrunch", "category": "ai", "relevance": 4},
            {"source": "techcrunch", "category": "ai", "relevance": 2},
            {"source": "reuters", "category": "policy", "relevance": 1},
        ]
        mock_get_client.return_value = self._build_mock_client(articles, [], [], 0)

        result = get_analytics()

        tc = result["source_quality"]["techcrunch"]
        assert tc["total"] == 3
        assert tc["high_relevance"] == 2  # relevance >= 4
        assert tc["signal_pct"] == 66.7  # 2/3 * 100

        r = result["source_quality"]["reuters"]
        assert r["total"] == 1
        assert r["high_relevance"] == 0
        assert r["signal_pct"] == 0

    @patch("lib.db._get_client")
    def test_category_distribution(self, mock_get_client):
        from lib.db import get_analytics
        articles = [
            {"source": "s1", "category": "ai", "relevance": 3},
            {"source": "s1", "category": "ai", "relevance": 4},
            {"source": "s2", "category": "policy", "relevance": 2},
        ]
        mock_get_client.return_value = self._build_mock_client(articles, [], [], 0)

        result = get_analytics()

        assert result["category_distribution"]["ai"] == 2
        assert result["category_distribution"]["policy"] == 1

    @patch("lib.db._get_client")
    def test_category_distribution_sorted_descending(self, mock_get_client):
        from lib.db import get_analytics
        articles = [
            {"source": "s", "category": "policy", "relevance": 1},
            {"source": "s", "category": "ai", "relevance": 1},
            {"source": "s", "category": "ai", "relevance": 1},
            {"source": "s", "category": "ai", "relevance": 1},
            {"source": "s", "category": "policy", "relevance": 1},
        ]
        mock_get_client.return_value = self._build_mock_client(articles, [], [], 0)

        result = get_analytics()
        cats = list(result["category_distribution"].keys())
        assert cats[0] == "ai"  # 3 articles
        assert cats[1] == "policy"  # 2 articles

    @patch("lib.db._get_client")
    def test_publish_stats(self, mock_get_client):
        from lib.db import get_analytics
        pub_data = [
            {"platform": "linkedin", "status": "published"},
            {"platform": "linkedin", "status": "published"},
            {"platform": "linkedin", "status": "failed"},
            {"platform": "devto", "status": "published"},
            {"platform": "devto", "status": "queued"},
        ]
        mock_get_client.return_value = self._build_mock_client([], pub_data, [], 0)

        result = get_analytics()

        li = result["publish_stats"]["linkedin"]
        assert li["total"] == 3
        assert li["published"] == 2
        assert li["failed"] == 1

        dt = result["publish_stats"]["devto"]
        assert dt["total"] == 2
        assert dt["published"] == 1
        assert dt["failed"] == 0

    @patch("lib.db._get_client")
    def test_briefings_count(self, mock_get_client):
        from lib.db import get_analytics
        briefings = [
            {"id": "b1", "email_sent": True},
            {"id": "b2", "email_sent": False},
            {"id": "b3", "email_sent": True},
        ]
        mock_get_client.return_value = self._build_mock_client([], [], briefings, 3)

        result = get_analytics()

        assert result["briefings"]["total"] == 3
        assert result["briefings"]["emailed"] == 2

    @patch("lib.db._get_client")
    def test_articles_total(self, mock_get_client):
        from lib.db import get_analytics
        articles = [
            {"source": "s", "category": "ai", "relevance": 3},
            {"source": "s", "category": "ai", "relevance": 4},
        ]
        mock_get_client.return_value = self._build_mock_client(articles, [], [], 0)

        result = get_analytics()
        assert result["articles_total"] == 2

    @patch("lib.db._get_client")
    def test_missing_relevance_treated_as_zero(self, mock_get_client):
        from lib.db import get_analytics
        articles = [
            {"source": "s", "category": "ai", "relevance": None},
            {"source": "s", "category": "ai"},  # missing key
        ]
        mock_get_client.return_value = self._build_mock_client(articles, [], [], 0)

        result = get_analytics()

        assert result["source_quality"]["s"]["high_relevance"] == 0
        assert result["source_quality"]["s"]["total"] == 2

    @patch("lib.db._get_client")
    def test_missing_source_defaults_to_unknown(self, mock_get_client):
        from lib.db import get_analytics
        articles = [
            {"category": "ai", "relevance": 5},  # no source key
        ]
        mock_get_client.return_value = self._build_mock_client(articles, [], [], 0)

        result = get_analytics()

        assert "unknown" in result["source_quality"]

    @patch("lib.db._get_client")
    def test_missing_category_defaults_to_other(self, mock_get_client):
        from lib.db import get_analytics
        articles = [
            {"source": "s", "relevance": 3},  # no category key
        ]
        mock_get_client.return_value = self._build_mock_client(articles, [], [], 0)

        result = get_analytics()

        assert "other" in result["category_distribution"]
