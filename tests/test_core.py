"""核心单元测试 — 覆盖纯函数和关键数据流。"""

from __future__ import annotations

import io

from pydub import AudioSegment

from assembler import _concat_wav_chunks, _sanitize_filename
from models import BookData, CleanedChapter
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

    def test_sentence_boundary_fallback(self):
        # 无段落边界时 fallback 到句子边界
        text = "第一句。第二句。第三句。" * 100
        chunks = chunk_text(text, max_chars=100)
        assert all(len(c) <= 100 for c in chunks)

    def test_extends_to_hard_limit(self):
        # 600 字内无自然边界时，向后扩展到 900 找最近边界
        # 构造一段 750 字的无标点文本，后面紧跟一个句号
        text = "A" * 750 + "。"
        chunks = chunk_text(text, max_chars=600)
        assert len(chunks) == 1
        assert len(chunks[0]) == 751  # 750 个 A + 句号

    def test_hard_cut_at_900(self):
        # 900 字内完全无边界时，硬切在 900
        text = "B" * 2000
        chunks = chunk_text(text, max_chars=600)
        assert len(chunks[0]) == 900
        assert len(chunks[1]) == 900
        assert len(chunks[2]) == 200

    def test_never_exceeds_hard_limit(self):
        # 任何 chunk 都不超过 hard limit（默认 900）
        text = "C" * 3000
        chunks = chunk_text(text, max_chars=600)
        assert all(len(c) <= 900 for c in chunks)


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

    def test_concat_multiple_chunks(self):
        """多段拼接应插入静音间隔。"""
        silence = AudioSegment.silent(duration=500, frame_rate=44100)
        wav_bytes = io.BytesIO()
        silence.export(wav_bytes, format="wav")
        chunk_bytes = wav_bytes.getvalue()

        result = _concat_wav_chunks([chunk_bytes, chunk_bytes])
        # 2 段 500ms 音频 + 1 段 1500ms 静音间隔 = 2500ms
        assert len(result) == 2500

    def test_concat_with_mixed_sample_rates(self):
        """不同采样率的 chunk 应统一。"""
        seg_44k = AudioSegment.silent(duration=500, frame_rate=44100)
        seg_22k = AudioSegment.silent(duration=500, frame_rate=22050)
        buf = io.BytesIO()
        seg_44k.export(buf, format="wav")
        buf2 = io.BytesIO()
        seg_22k.export(buf2, format="wav")
        result = _concat_wav_chunks([buf.getvalue(), buf2.getvalue()])
        # 500 + 1500(间隔) + 500 = 2500
        assert len(result) == 2500

    def test_concat_ignores_empty_chunks(self):
        """空的 chunk bytes 应被跳过。只剩一个有效段时不插静音。"""
        seg = AudioSegment.silent(duration=500, frame_rate=44100)
        buf = io.BytesIO()
        seg.export(buf, format="wav")
        result = _concat_wav_chunks([b"", buf.getvalue(), b""])
        assert len(result) == 500  # 空段被跳过，只剩一段，不插静音

    def test_sanitize_filename(self):
        assert ":" not in _sanitize_filename("a:b")
        assert "?" not in _sanitize_filename("a?b")
        assert "/" not in _sanitize_filename("a/b")
        assert "\\" not in _sanitize_filename("a\\b")
        assert "*" not in _sanitize_filename("a*b")

    def test_export_to_mp3_sets_channels(self, monkeypatch, tmp_path):
        """export_to_mp3 应设置声道数为 1。"""
        from assembler import export_to_mp3

        export_calls = []

        class FakeSegment:
            def set_channels(self, n):
                export_calls.append(("set_channels", n))
                return self

            def export(self, path, **kw):
                export_calls.append(("export", str(path), kw))

        export_to_mp3(FakeSegment(), tmp_path / "test.mp3", bitrate="128k")
        assert ("set_channels", 1) in export_calls
        assert any(c[0] == "export" for c in export_calls)

    def test_write_id3_tags(self, monkeypatch, tmp_path):
        """write_id3_tags 应调用 add 4 次（TIT2/TPE1/TALB/TRCK）+ save 1 次。"""
        from assembler import write_id3_tags

        call_count = {"mp3": 0, "add_tags": 0, "add": 0, "save": 0}

        class FakeTags:
            def add(self, tag):
                call_count["add"] += 1

            def save(self, path):
                call_count["save"] += 1

        class FakeAudio:
            tags = None

            def __init__(self, _path):
                call_count["mp3"] += 1

            def add_tags(self):
                call_count["add_tags"] += 1
                self.tags = FakeTags()
                return self.tags

        monkeypatch.setattr("assembler.MP3", FakeAudio)

        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_text("fake")
        write_id3_tags(mp3_path, "Book", "Author", "Ch1", 1)

        assert call_count["add"] == 4  # TIT2, TPE1, TALB, TRCK
        assert call_count["save"] == 1
        assert call_count["mp3"] >= 1


class TestModels:
    def test_bookdata_defaults(self):
        book = BookData(title="Test", author="Author")
        assert book.language == "zh"
        assert book.chapters == []

    def test_cleanedchapter(self):
        ch = CleanedChapter(title="Ch1", chunks=["a", "b"])
        assert ch.title == "Ch1"
        assert len(ch.chunks) == 2
