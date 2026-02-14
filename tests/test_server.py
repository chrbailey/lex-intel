"""Tests for lex_server.py — signal clustering logic in lex_get_signals."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_article(source, english_title, category="funding", relevance=5, published_at="2026-02-14"):
    """Helper to build a fake article row matching Supabase schema."""
    return {
        "source": source,
        "english_title": english_title,
        "category": category,
        "relevance": relevance,
        "published_at": published_at,
    }


def _mock_supabase_with_articles(articles):
    """Build a mock Supabase client that returns the given articles from
    the articles table query chain used by lex_get_signals."""
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_result.data = articles

    # Chain: client.table("articles").select(...).gte(...).gte(...).order(...).order(...).limit(...).execute()
    chain = mock_client.table.return_value
    chain = chain.select.return_value
    chain = chain.gte.return_value
    chain = chain.gte.return_value
    chain = chain.order.return_value
    chain = chain.order.return_value
    chain = chain.limit.return_value
    chain.execute.return_value = mock_result

    return mock_client


class TestSignalClustering:
    """Tests for article clustering by shared keywords in lex_get_signals."""

    @patch("lib.db._get_client")
    def test_clusters_articles_with_shared_keywords(self, mock_get_client):
        """Articles from different sources sharing 2+ keywords cluster together."""
        articles = [
            _make_article("36kr", "DeepSeek releases open source language model", "breakthrough"),
            _make_article("huxiu", "DeepSeek launches new open source model for developers", "breakthrough"),
            _make_article("csdn", "Alibaba Cloud releases pricing update", "product"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        signals = result["signals"]
        # The two DeepSeek articles should cluster; Alibaba is separate
        deepseek_cluster = None
        for s in signals:
            sources_in_cluster = [a["source"] for a in s["articles"]]
            if "36kr" in sources_in_cluster and "huxiu" in sources_in_cluster:
                deepseek_cluster = s
                break

        assert deepseek_cluster is not None, "DeepSeek articles should cluster together"
        assert len(deepseek_cluster["articles"]) == 2
        assert deepseek_cluster["source_count"] == 2

    @patch("lib.db._get_client")
    def test_different_category_prevents_clustering(self, mock_get_client):
        """Articles with shared keywords but different categories stay separate."""
        articles = [
            _make_article("36kr", "DeepSeek releases open source model", "breakthrough"),
            _make_article("huxiu", "DeepSeek open source model funding round", "funding"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        signals = result["signals"]
        assert len(signals) == 2, "Different categories should not cluster"
        for s in signals:
            assert len(s["articles"]) == 1

    @patch("lib.db._get_client")
    def test_confidence_high_three_plus_sources(self, mock_get_client):
        """3+ unique sources in a cluster => confidence 'high'."""
        articles = [
            _make_article("36kr", "Robotics startup funding round completed", "funding"),
            _make_article("huxiu", "Major robotics funding announced this round", "funding"),
            _make_article("caixin", "Robotics companies complete new funding round", "funding"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        signals = result["signals"]
        cluster = signals[0]
        assert cluster["confidence"] == "high"
        assert cluster["source_count"] >= 3

    @patch("lib.db._get_client")
    def test_confidence_medium_two_sources(self, mock_get_client):
        """2 unique sources in a cluster => confidence 'medium'."""
        articles = [
            _make_article("36kr", "Semiconductor export controls tightened again", "regulation"),
            _make_article("caixin", "Export controls semiconductor restrictions expanded", "regulation"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        signals = result["signals"]
        cluster = signals[0]
        assert cluster["confidence"] == "medium"
        assert cluster["source_count"] == 2

    @patch("lib.db._get_client")
    def test_confidence_single_source(self, mock_get_client):
        """1 source => confidence 'single-source'."""
        articles = [
            _make_article("36kr", "Unique story only one outlet covered", "product"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        signals = result["signals"]
        assert len(signals) == 1
        assert signals[0]["confidence"] == "single-source"
        assert signals[0]["source_count"] == 1

    @patch("lib.db._get_client")
    def test_clusters_sorted_by_source_count_descending(self, mock_get_client):
        """Clusters should be sorted by source_count descending."""
        articles = [
            # 3-source cluster (robotics)
            _make_article("36kr", "Robotics startup expansion funding", "funding"),
            _make_article("huxiu", "Robotics company expansion gets funding", "funding"),
            _make_article("caixin", "Robotics expansion plan receives funding", "funding"),
            # 1-source cluster (regulation)
            _make_article("csdn", "Unique regulation story alone", "regulation"),
            # 2-source cluster (chip)
            _make_article("36kr", "Advanced chip manufacturing breakthrough reported", "breakthrough"),
            _make_article("huxiu", "Chip manufacturing reaches breakthrough milestone", "breakthrough"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        signals = result["signals"]
        assert len(signals) >= 3

        source_counts = [s["source_count"] for s in signals]
        assert source_counts == sorted(source_counts, reverse=True), \
            f"Should be sorted descending by source_count, got {source_counts}"

    @patch("lib.db._get_client")
    def test_empty_results(self, mock_get_client):
        """No articles => no signals."""
        mock_get_client.return_value = _mock_supabase_with_articles([])

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        assert result["signals"] == []
        assert result["total"] == 0
        assert result["signal_count"] == 0

    @patch("lib.db._get_client")
    def test_single_article(self, mock_get_client):
        """One article => one single-source signal."""
        articles = [
            _make_article("36kr", "Sole article about quantum computing", "breakthrough"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        assert result["signal_count"] == 1
        assert result["total"] == 1
        assert result["signals"][0]["confidence"] == "single-source"

    @patch("lib.db._get_client")
    def test_all_same_source_stays_single_cluster(self, mock_get_client):
        """Multiple articles from same source with shared keywords => one cluster, source_count=1."""
        articles = [
            _make_article("36kr", "Robotics factory automation advances rapidly", "product"),
            _make_article("36kr", "Factory automation robotics deployed widely", "product"),
            _make_article("36kr", "Robotics automation factory output increases", "product"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        signals = result["signals"]
        # All should cluster (shared keywords + same category)
        assert len(signals) == 1
        assert signals[0]["source_count"] == 1
        assert signals[0]["confidence"] == "single-source"
        assert len(signals[0]["articles"]) == 3

    @patch("lib.db._get_client")
    def test_unicode_titles_in_clustering(self, mock_get_client):
        """Unicode titles should not crash keyword extraction."""
        articles = [
            _make_article("weixin", "人工智能发展报告2026", "research"),
            _make_article("36kr", "中国AI芯片突破性进展", "breakthrough"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        # Should not raise, and each stays separate (no shared 3+ letter ASCII keywords)
        assert result["signal_count"] == 2

    @patch("lib.db._get_client")
    def test_no_clustering_without_shared_keywords(self, mock_get_client):
        """Articles in same category but with no shared keywords stay separate."""
        articles = [
            _make_article("36kr", "Quantum computing breakthrough reported", "breakthrough"),
            _make_article("huxiu", "Semiconductor manufacturing facility opens", "breakthrough"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        signals = result["signals"]
        assert len(signals) == 2
        for s in signals:
            assert len(s["articles"]) == 1
            assert s["confidence"] == "single-source"

    @patch("lib.db._get_client")
    def test_transitive_clustering(self, mock_get_client):
        """Article C clusters with A through B (transitive keyword expansion)."""
        articles = [
            # A and B share "robotics" + "startup"
            _make_article("36kr", "Robotics startup launches product line", "product"),
            _make_article("huxiu", "Robotics startup raises series funding", "product"),
            # After A+B merge: kw_a includes {robotics, startup, launches, product, line, raises, series, funding}
            # C shares "raises" + "series" with the expanded set => clusters
            _make_article("caixin", "Company raises series capital for expansion", "product"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        signals = result["signals"]
        # All three should transitively cluster
        assert len(signals) == 1
        assert signals[0]["source_count"] == 3
        assert signals[0]["confidence"] == "high"

    @patch("lib.db._get_client")
    def test_result_structure(self, mock_get_client):
        """Verify the full structure of the returned dict."""
        articles = [
            _make_article("36kr", "Test article title here", "funding", 5, "2026-02-14"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        # Top-level keys
        assert "signals" in result
        assert "total" in result
        assert "signal_count" in result
        assert "period" in result
        assert "min_relevance" in result

        assert result["period"] == "last 7 days"
        assert result["min_relevance"] == 4

        # Signal structure
        signal = result["signals"][0]
        assert "theme" in signal
        assert "category" in signal
        assert "source_count" in signal
        assert "sources" in signal
        assert "confidence" in signal
        assert "articles" in signal

        # Article within signal
        article = signal["articles"][0]
        assert article["source"] == "36kr"
        assert article["english_title"] == "Test article title here"
        assert article["relevance"] == 5
        assert article["published_at"] == "2026-02-14"

    @patch("lib.db._get_client")
    def test_theme_is_first_article_title_truncated(self, mock_get_client):
        """Theme should be the first article's english_title, truncated to 80 chars."""
        long_title = "A" * 200
        articles = [
            _make_article("36kr", long_title, "product"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        theme = result["signals"][0]["theme"]
        assert len(theme) == 80
        assert theme == "A" * 80

    @patch("lib.db._get_client")
    def test_days_clamped_to_valid_range(self, mock_get_client):
        """days parameter is clamped between 1 and 30."""
        mock_get_client.return_value = _mock_supabase_with_articles([])

        from lex_server import lex_get_signals

        result = lex_get_signals(days=0, min_relevance=4)
        assert result["period"] == "last 1 days"

        result = lex_get_signals(days=100, min_relevance=4)
        assert result["period"] == "last 30 days"

    @patch("lib.db._get_client")
    def test_stop_words_excluded_from_keywords(self, mock_get_client):
        """Common stop words should not contribute to keyword matching."""
        articles = [
            # These share stop words (the, and, for, with, new) but no content words
            _make_article("36kr", "The new platform for developers", "product"),
            _make_article("huxiu", "The new framework with features", "product"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        signals = result["signals"]
        # "the", "new", "for", "with" are stop words, so these shouldn't cluster
        # Only non-stop words: {platform, developers} vs {framework, features} — no overlap
        assert len(signals) == 2

    @patch("lib.db._get_client")
    def test_missing_english_title_handled(self, mock_get_client):
        """Article with missing english_title should not crash."""
        articles = [
            {"source": "36kr", "category": "product", "relevance": 5, "published_at": "2026-02-14"},
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        assert result["signal_count"] == 1
        assert result["signals"][0]["articles"][0]["english_title"] == ""

    @patch("lib.db._get_client")
    def test_published_at_truncated_to_date(self, mock_get_client):
        """published_at in article output should be date-only (first 10 chars)."""
        articles = [
            _make_article("36kr", "Test", "product", 5, "2026-02-14T08:30:00Z"),
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        assert result["signals"][0]["articles"][0]["published_at"] == "2026-02-14"

    @patch("lib.db._get_client")
    def test_published_at_none_handled(self, mock_get_client):
        """published_at=None should not crash, should produce empty string."""
        articles = [
            {"source": "36kr", "english_title": "Test", "category": "product",
             "relevance": 5, "published_at": None},
        ]
        mock_get_client.return_value = _mock_supabase_with_articles(articles)

        from lex_server import lex_get_signals
        result = lex_get_signals(days=7, min_relevance=4)

        assert result["signals"][0]["articles"][0]["published_at"] == ""
