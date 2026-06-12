"""parser 纯函数单元测试 — 不涉及 EPUB/PDF 文件 IO。"""

from __future__ import annotations

from models import Chapter
from parser import (
    _clean_metadata_lines,
    _extract_title_from_html,
    _is_toc_page,
    _strip_html,
    chunk_text,
    detect_language,
)


class TestStripHtml:
    def test_removes_simple_tags(self):
        assert _strip_html("<p>Hello</p>") == "Hello"

    def test_removes_script_tag(self):
        html = "<script>alert('x')</script><p>正文</p>"
        assert "alert" not in _strip_html(html)
        assert "正文" in _strip_html(html)

    def test_removes_style_tag(self):
        html = "<style>.cls{color:red}</style><p>内容</p>"
        assert "color" not in _strip_html(html)
        assert "内容" in _strip_html(html)

    def test_returns_text_separated_by_newlines(self):
        html = "<div><p>第一段</p><p>第二段</p></div>"
        result = _strip_html(html)
        assert "第一段" in result
        assert "第二段" in result

    def test_empty_html(self):
        assert _strip_html("") == ""


class TestIsTocPage:
    def test_short_text_is_toc(self):
        assert _is_toc_page("目录") is True

    def test_blank_text_is_toc(self):
        assert _is_toc_page("   ") is True

    def test_long_text_is_not_toc(self):
        assert _is_toc_page("这是一段足够长的正文内容，超过了最小阈值。" * 10) is False


class TestCleanMetadataLines:
    def test_removes_source_line(self):
        result = _clean_metadata_lines("来源于某处\n这是正文")
        assert "来源于" not in result

    def test_removes_copyright_line(self):
        result = _clean_metadata_lines("Copyright 2026\n这是正文")
        assert "Copyright" not in result

    def test_removes_published_by(self):
        result = _clean_metadata_lines("Published by Penguin\n这是正文")
        assert "Published" not in result

    def test_removes_ting_baodao(self):
        result = _clean_metadata_lines("听报道\n这是正文")
        assert "听报道" not in result

    def test_preserves_normal_text(self):
        text = "这是正常的正文内容。\n第二段内容。"
        assert _clean_metadata_lines(text) == text

    def test_multiple_keyword_lines(self):
        result = _clean_metadata_lines("来源于A\nCopyright B\n返回目录\n正文")
        assert "来源于" not in result
        assert "Copyright" not in result
        assert "返回目录" not in result
        assert "正文" in result


class TestExtractTitleFromHtml:
    def test_extracts_h1(self):
        html = "<h1>第一章 旅程开始</h1><p>正文内容</p>"
        text = "正文内容"
        assert _extract_title_from_html(html, text, []) == "第一章 旅程开始"

    def test_extracts_h2(self):
        html = "<h2>背景介绍</h2><p>详细内容</p>"
        text = "详细内容"
        assert _extract_title_from_html(html, text, []) == "背景介绍"

    def test_extracts_h3(self):
        html = "<h3>小节标题</h3><p>内容</p>"
        text = "内容"
        assert _extract_title_from_html(html, text, []) == "小节标题"

    def test_fallback_to_first_line(self):
        html = "<p>第一行文字</p><p>正文</p>"
        text = "第一行文字\n正文"
        assert _extract_title_from_html(html, text, []) == "第一行文字"

    def test_fallback_when_heading_too_long(self):
        html = "<h1>" + "A" * 200 + "</h1><p>正文</p>"
        text = "正文"
        assert _extract_title_from_html(html, text, []) == "正文"

    def test_unnamed_fallback(self):
        html = "<p></p>"
        text = ""
        assert _extract_title_from_html(html, text, []) == "未命名章节"


class TestDetectLanguageFromChapters:
    def test_chinese_books(self):
        chapters = [Chapter(title="第一章", chunks=["这是一个中文测试文本。"])]
        assert detect_language(chapters) == "zh"

    def test_english_books(self):
        chapters = [Chapter(title="Chapter 1", chunks=["This is an English test."])]
        assert detect_language(chapters) == "en"

    def test_empty_chapters_defaults_zh(self):
        assert detect_language([]) == "zh"

    def test_mixed_content_prefers_zh(self):
        """parser.detect_language 阈值是 0.3，需要更多中文。"""
        chapters = [Chapter(title="混合", chunks=["中文" * 12 + " mixed with some English"])]
        assert detect_language(chapters) == "zh"


class TestChunkTextEdgeCases:
    def test_empty_text(self):
        assert chunk_text("") == []

    def test_whitespace_only(self):
        assert chunk_text("   ") == []

    def test_single_short_paragraph(self):
        assert chunk_text("hello world") == ["hello world"]

    def test_sentence_boundary_fallback_with_multiple_sentences(self):
        """句子边界被优先于硬切——在 soft limit 内取最后一个句子边界。"""
        text = "第一句。" + "第二句。" + "第三句。" + "A" * 300
        chunks = chunk_text(text, max_chars=50)
        # 第一个 chunk 应在第三句句号处截断
        assert len(chunks) >= 2
        assert chunks[0].endswith("。")
        assert "A" not in chunks[0]

    def test_sentence_boundary_in_soft_hard_range(self):
        """soft~hard 区间内找到句子边界时，在边界处切分。"""
        text = "A" * 650 + "。" + "B" * 200
        chunks = chunk_text(text, max_chars=600)
        assert len(chunks) == 2
        assert chunks[0].endswith("。")
        assert chunks[1].startswith("B")

    def test_extends_to_hard_limit_for_para_boundary(self):
        """soft~hard 区间内找段落边界。"""
        text = "A" * 650 + "\n\n" + "B" * 200
        chunks = chunk_text(text, max_chars=600)
        # 应在段落边界切分（> 600 但 < 900）
        assert len(chunks) == 2
        assert chunks[0].endswith("A" * 650)

    def test_extends_to_hard_limit_for_sentence_boundary(self):
        """soft~hard 区间内找句子边界。"""
        text = "A" * 650 + "。" + "B" * 200
        chunks = chunk_text(text, max_chars=600)
        assert len(chunks) == 2
        assert chunks[0].endswith("。")

    def test_hard_cut_at_900_when_no_boundary(self):
        """900 字内完全无边界时硬切。"""
        text = "B" * 2000
        chunks = chunk_text(text, max_chars=600)
        assert all(len(c) <= 900 for c in chunks)
        assert len(chunks[0]) == 900

    def test_never_exceeds_hard_limit(self):
        """任何 chunk 不超过硬限制。"""
        text = "C" * 5000
        chunks = chunk_text(text, max_chars=600)
        assert all(len(c) <= 900 for c in chunks)

    def test_text_with_no_punctuation_or_breaks(self):
        """无标点无换行的极端情况。"""
        text = "X" * 3000
        chunks = chunk_text(text, max_chars=600)
        assert all(len(c) <= 900 for c in chunks)
        # 最后一个 chunk 可能不足 900
        assert sum(len(c) for c in chunks) == 3000

    def test_para_boundary_preferred_over_sentence(self):
        """段落边界优先级高于句子边界。"""
        text_para = "第一段内容。" * 10 + "\n\n" + "第二段内容。" * 10
        chunks_para = chunk_text(text_para, max_chars=100)
        # 有段落边界的应在段落处切分
        assert len(chunks_para) >= 2
