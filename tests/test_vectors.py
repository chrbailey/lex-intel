"""Tests for lib/vectors.py — Pinecone vector layer."""
from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest


class TestArticleId:
    """Tests for _article_id(source, title) — deterministic SHA256 hash."""

    def test_deterministic(self):
        from lib.vectors import _article_id

        id1 = _article_id("36kr", "AI芯片突破")
        id2 = _article_id("36kr", "AI芯片突破")
        assert id1 == id2

    def test_length_is_16(self):
        from lib.vectors import _article_id

        result = _article_id("huxiu", "Some article title")
        assert len(result) == 16

    def test_hex_characters_only(self):
        from lib.vectors import _article_id

        result = _article_id("csdn", "Test")
        assert all(c in "0123456789abcdef" for c in result)

    def test_matches_manual_sha256(self):
        from lib.vectors import _article_id

        source, title = "caixin", "DeepSeek发布新模型"
        expected = hashlib.sha256(f"{source}:{title}".encode()).hexdigest()[:16]
        assert _article_id(source, title) == expected

    def test_different_source_different_id(self):
        from lib.vectors import _article_id

        id1 = _article_id("36kr", "Same Title")
        id2 = _article_id("huxiu", "Same Title")
        assert id1 != id2

    def test_different_title_different_id(self):
        from lib.vectors import _article_id

        id1 = _article_id("36kr", "Title A")
        id2 = _article_id("36kr", "Title B")
        assert id1 != id2

    def test_empty_strings(self):
        from lib.vectors import _article_id

        result = _article_id("", "")
        expected = hashlib.sha256(b":").hexdigest()[:16]
        assert result == expected
        assert len(result) == 16

    def test_unicode_title(self):
        from lib.vectors import _article_id

        result = _article_id("weixin", "中国人工智能发展报告2026")
        assert len(result) == 16
        # Verify consistency with Unicode
        assert result == _article_id("weixin", "中国人工智能发展报告2026")

    def test_special_characters(self):
        from lib.vectors import _article_id

        result = _article_id("src", "Title: with (special) & chars!")
        assert len(result) == 16


class TestMakeContent:
    """Tests for _make_content(english_title, body) — content field builder."""

    def test_basic_format(self):
        from lib.vectors import _make_content

        result = _make_content("My Title", "Body text here")
        assert result == "My Title\n\nBody text here"

    def test_format_is_title_double_newline_body(self):
        from lib.vectors import _make_content

        result = _make_content("Title", "Body")
        parts = result.split("\n\n", 1)
        assert len(parts) == 2
        assert parts[0] == "Title"
        assert parts[1] == "Body"

    def test_body_truncated_at_2000(self):
        from lib.vectors import _make_content

        long_body = "x" * 3000
        result = _make_content("Title", long_body)
        # Title + \n\n + 2000 chars
        assert result == f"Title\n\n{'x' * 2000}"

    def test_body_exactly_2000_not_truncated(self):
        from lib.vectors import _make_content

        body = "a" * 2000
        result = _make_content("Title", body)
        assert result == f"Title\n\n{body}"

    def test_body_under_2000_not_truncated(self):
        from lib.vectors import _make_content

        body = "Short body"
        result = _make_content("Title", body)
        assert result == "Title\n\nShort body"

    def test_empty_body(self):
        from lib.vectors import _make_content

        result = _make_content("Title", "")
        assert result == "Title\n\n"

    def test_empty_title(self):
        from lib.vectors import _make_content

        result = _make_content("", "Some body")
        assert result == "\n\nSome body"

    def test_both_empty(self):
        from lib.vectors import _make_content

        result = _make_content("", "")
        assert result == "\n\n"

    def test_unicode_content(self):
        from lib.vectors import _make_content

        result = _make_content("AI芯片突破", "中国科技公司发布新芯片")
        assert result == "AI芯片突破\n\n中国科技公司发布新芯片"

    def test_title_not_truncated(self):
        from lib.vectors import _make_content

        long_title = "T" * 5000
        result = _make_content(long_title, "body")
        assert result.startswith("T" * 5000)


class TestUpsertArticles:
    """Tests for upsert_articles(articles) — batch Pinecone upsert."""

    @patch("lib.vectors._get_index")
    def test_empty_list_returns_zero(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        result = upsert_articles([])
        assert result == 0
        mock_index.upsert_records.assert_not_called()

    @patch("lib.vectors._get_index")
    def test_no_index_returns_zero(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_get_index.return_value = None
        result = upsert_articles([{"source": "36kr", "title": "Test"}])
        assert result == 0

    @patch("lib.vectors._get_index")
    def test_single_article_upserted(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        articles = [{
            "source": "36kr",
            "title": "测试文章",
            "english_title": "Test Article",
            "body": "Article body content",
            "category": "funding",
            "relevance": 4,
            "published_at": "2026-02-14",
        }]

        result = upsert_articles(articles)
        assert result == 1
        mock_index.upsert_records.assert_called_once()

        # Verify the record passed to Pinecone
        call_args = mock_index.upsert_records.call_args
        namespace = call_args[0][0]
        batch = call_args[0][1]
        assert namespace == "lex-articles"
        assert len(batch) == 1
        record = batch[0]
        assert record["source"] == "36kr"
        assert record["category"] == "funding"
        assert record["relevance"] == 4
        assert "Test Article" in record["content"]

    @patch("lib.vectors._get_index")
    def test_batch_splitting_at_50(self, mock_get_index):
        from lib.vectors import upsert_articles, BATCH_SIZE

        assert BATCH_SIZE == 50, "BATCH_SIZE should be 50"

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        # 120 articles -> 3 batches: 50, 50, 20
        articles = [
            {"source": f"src_{i}", "title": f"Title {i}", "body": f"Body {i}"}
            for i in range(120)
        ]

        result = upsert_articles(articles)
        assert result == 120
        assert mock_index.upsert_records.call_count == 3

        # Verify batch sizes
        calls = mock_index.upsert_records.call_args_list
        assert len(calls[0][0][1]) == 50
        assert len(calls[1][0][1]) == 50
        assert len(calls[2][0][1]) == 20

    @patch("lib.vectors._get_index")
    def test_exactly_50_is_single_batch(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        articles = [
            {"source": "s", "title": f"Title {i}"}
            for i in range(50)
        ]

        result = upsert_articles(articles)
        assert result == 50
        assert mock_index.upsert_records.call_count == 1

    @patch("lib.vectors._get_index")
    def test_51_articles_is_two_batches(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        articles = [
            {"source": "s", "title": f"Title {i}"}
            for i in range(51)
        ]

        result = upsert_articles(articles)
        assert result == 51
        assert mock_index.upsert_records.call_count == 2

        calls = mock_index.upsert_records.call_args_list
        assert len(calls[0][0][1]) == 50
        assert len(calls[1][0][1]) == 1

    @patch("lib.vectors._get_index")
    def test_missing_fields_use_defaults(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        # Minimal article — only required to not crash
        articles = [{}]
        result = upsert_articles(articles)
        assert result == 1

        record = mock_index.upsert_records.call_args[0][1][0]
        assert record["source"] == "unknown"
        assert record["category"] == "other"
        assert record["relevance"] == 1
        assert record["published_at"] == ""
        assert record["article_id"] == ""

    @patch("lib.vectors._get_index")
    def test_english_title_falls_back_to_title(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        articles = [{"source": "s", "title": "原始标题"}]
        upsert_articles(articles)

        record = mock_index.upsert_records.call_args[0][1][0]
        assert record["english_title"] == "原始标题"
        assert "原始标题" in record["content"]

    @patch("lib.vectors._get_index")
    def test_body_falls_back_to_content_field(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        articles = [{"source": "s", "title": "T", "content": "Fallback content"}]
        upsert_articles(articles)

        record = mock_index.upsert_records.call_args[0][1][0]
        assert "Fallback content" in record["content"]

    @patch("lib.vectors._get_index")
    def test_english_title_truncated_to_500(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        long_title = "A" * 1000
        articles = [{"source": "s", "title": "t", "english_title": long_title}]
        upsert_articles(articles)

        record = mock_index.upsert_records.call_args[0][1][0]
        assert len(record["english_title"]) == 500

    @patch("lib.vectors._get_index")
    def test_batch_failure_continues_remaining(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        # First batch fails, second succeeds
        mock_index.upsert_records.side_effect = [
            Exception("Pinecone timeout"),
            None,
        ]

        articles = [
            {"source": "s", "title": f"Title {i}"}
            for i in range(75)  # 2 batches: 50 + 25
        ]

        result = upsert_articles(articles)
        # First batch failed (0), second succeeded (25)
        assert result == 25
        assert mock_index.upsert_records.call_count == 2

    @patch("lib.vectors._get_index")
    def test_article_id_uses_source_and_title(self, mock_get_index):
        from lib.vectors import upsert_articles, _article_id

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        articles = [{"source": "huxiu", "title": "AI News"}]
        upsert_articles(articles)

        record = mock_index.upsert_records.call_args[0][1][0]
        expected_id = _article_id("huxiu", "AI News")
        assert record["_id"] == expected_id

    @patch("lib.vectors._get_index")
    def test_article_id_field_prefers_article_id_key(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        articles = [{"source": "s", "title": "t", "article_id": "uuid-123"}]
        upsert_articles(articles)

        record = mock_index.upsert_records.call_args[0][1][0]
        assert record["article_id"] == "uuid-123"

    @patch("lib.vectors._get_index")
    def test_article_id_field_falls_back_to_id(self, mock_get_index):
        from lib.vectors import upsert_articles

        mock_index = MagicMock()
        mock_get_index.return_value = mock_index

        articles = [{"source": "s", "title": "t", "id": "fallback-id"}]
        upsert_articles(articles)

        record = mock_index.upsert_records.call_args[0][1][0]
        assert record["article_id"] == "fallback-id"
