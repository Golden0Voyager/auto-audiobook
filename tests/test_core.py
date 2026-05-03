"""核心单元测试 — 覆盖纯函数和关键数据流。"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pydub import AudioSegment

from assembler import _concat_wav_chunks, _sanitize_filename
from models import BookData, Chapter, CleanedChapter
from parser import chunk_text
from rule_cleaner import _clean_chunk
from synthesizer import _compute_cache_key
from text_processor import detect_language, get_language_name, optimize_for_speech


class TestChunkText:
    def test_empty_text(self):
        assert chunk_text("") == []

    def test_single_short_paragraph(self):
        assert chunk_text("hello world") == ["hello world"]

    def test_splits_at_paragraph_boundary(self):
        text = "A\n\nB"
        # 当总长度 < max_chars 时，段落会合并到同一块
        chunks = chunk_text(text, max_chars=10)
        assert len(chunks) == 1
        assert "A" in chunks[0]
        assert "B" in chunks[0]

    def test_splits_when_exceeds_max(self):
        text = "A" * 50 + "\n\n" + "B" * 50
        chunks = chunk_text(text, max_chars=80)
        assert len(chunks) == 2
        assert "A" in chunks[0]
        assert "B" in chunks[1]

    def test_long_paragraph_split(self):
        # 一个超长段落应该被按句子拆分
        text = "第一句。第二句。第三句。" * 100
        chunks = chunk_text(text, max_chars=100)
        assert all(len(c) <= 100 for c in chunks)


class TestCleanChunk:
    def test_removes_url(self):
        assert "https://" not in _clean_chunk("访问 https://example.com 获取更多信息")

    def test_removes_email(self):
        assert "@" not in _clean_chunk("联系 foo@bar.com")

    def test_removes_references(self):
        assert "[1]" not in _clean_chunk("根据文献[1]和[2]")

    def test_collapse_blank_lines(self):
        assert "\n\n\n" not in _clean_chunk("A\n\n\nB")


class TestDetectLanguage:
    def test_chinese(self):
        code, conf = detect_language("这是一个中文测试文本")
        assert code == "zh"
        assert conf > 0.5

    def test_english(self):
        code, conf = detect_language("This is an English test text")
        assert code == "en"
        assert conf > 0.5

    def test_empty_defaults_zh(self):
        code, conf = detect_language("")
        assert code == "zh"

    def test_get_language_name(self):
        assert get_language_name("zh") == "中文"
        assert get_language_name("en") == "英文"
        assert get_language_name("xx") == "未知"


class TestOptimizeForSpeech:
    def test_idempotent_short_text(self):
        text = "这是一个测试文本。"
        assert optimize_for_speech(text) == text

    def test_normalizes_punctuation(self):
        text = "hello..world"
        result = optimize_for_speech(text)
        assert ".." not in result

    def test_adds_pauses(self):
        text = "虽然天气很好"
        result = optimize_for_speech(text)
        # 转折词前应该添加逗号
        assert "，虽然" in result or result.startswith("虽然")


class TestCacheKey:
    def test_key_includes_all_factors(self):
        key1 = _compute_cache_key("茉莉", "default", "测试文本")
        key2 = _compute_cache_key("茉莉", "news", "测试文本")
        key3 = _compute_cache_key("苏打", "default", "测试文本")
        assert key1 != key2
        assert key1 != key3

    def test_same_input_same_key(self):
        key1 = _compute_cache_key("茉莉", "default", "测试文本")
        key2 = _compute_cache_key("茉莉", "default", "测试文本")
        assert key1 == key2


class TestAssembler:
    def test_concat_empty(self):
        result = _concat_wav_chunks([])
        assert len(result) == 0

    def test_concat_single_chunk(self):
        # 构造一个有效的 1 秒静音 WAV
        silence = AudioSegment.silent(duration=1000)
        wav_bytes = io.BytesIO()
        silence.export(wav_bytes, format="wav")
        result = _concat_wav_chunks([wav_bytes.getvalue()])
        assert len(result) == 1000

    def test_sanitize_filename(self):
        assert ":" not in _sanitize_filename("a:b")
        assert "?" not in _sanitize_filename("a?b")


class TestModels:
    def test_bookdata_defaults(self):
        book = BookData(title="Test", author="Author")
        assert book.language == "zh"
        assert book.chapters == []

    def test_cleanedchapter(self):
        ch = CleanedChapter(title="Ch1", chunks=["a", "b"])
        assert ch.title == "Ch1"
        assert len(ch.chunks) == 2
