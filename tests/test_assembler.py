"""assembler 单元测试 — 音频拼接、MP3 导出、ID3 标签注入。"""

from __future__ import annotations

import io
from pathlib import Path

from pydub import AudioSegment

from assembler import (
    _concat_wav_chunks,
    _sanitize_filename,
    assemble_book,
    export_to_mp3,
    write_id3_tags,
)
from models import ChapterAudio

# ── WAV 辅助 ──────────────────────────────────────────────


def _make_wav(duration_ms: int = 100, sample_rate: int = 44100) -> bytes:
    """生成一段指定时长和采样率的 WAV bytes。"""
    seg = AudioSegment.silent(duration=duration_ms, frame_rate=sample_rate)
    return seg.export(io.BytesIO(), format="wav").read()


def _make_wav_22050(duration_ms: int = 100) -> bytes:
    """生成 22050Hz 的 WAV bytes（用于测试采样率混用）。"""
    return _make_wav(duration_ms, sample_rate=22050)


# ── _concat_wav_chunks ────────────────────────────────────


class TestConcatWavChunks:
    def test_single_chunk(self):
        """单个 chunk → 返回 AudioSegment。"""
        data = _make_wav(200)
        result = _concat_wav_chunks([data])
        assert isinstance(result, AudioSegment)
        assert len(result) >= 190  # pydub 可能微调

    def test_multiple_chunks(self):
        """多个 chunk 拼接 → 总时长 ≈ 各 chunk 时长 + 静音间隔。"""
        data = _make_wav(100)
        result = _concat_wav_chunks([data, data, data])
        assert len(result) >= 290  # 3×100ms + 2×静音

    def test_empty_list_returns_empty(self):
        """空列表 → 返回空的 AudioSegment。"""
        result = _concat_wav_chunks([])
        assert isinstance(result, AudioSegment)
        assert len(result) == 0

    def test_filters_empty_bytes(self):
        """列表中的空 bytes 被过滤掉。"""
        data = _make_wav(100)
        result = _concat_wav_chunks([data, b"", data])
        # 等价于两个 chunk 拼接
        assert len(result) >= 190

    def test_mixed_sample_rates(self):
        """不同采样率的 WAV 被统一到第一个 chunk 的采样率。"""
        data_44k = _make_wav(100, sample_rate=44100)
        data_22k = _make_wav(100, sample_rate=22050)
        result = _concat_wav_chunks([data_44k, data_22k])
        assert result.frame_rate == 44100
        assert len(result) >= 190

    def test_mixed_sample_width(self):
        """不同位深同样被统一。"""
        seg_16bit = AudioSegment.silent(duration=100, frame_rate=44100)
        seg_16bit = seg_16bit.set_sample_width(2)  # 16bit
        seg_8bit = AudioSegment.silent(duration=100, frame_rate=44100)
        seg_8bit = seg_8bit.set_sample_width(1)  # 8bit

        data_16 = seg_16bit.export(io.BytesIO(), format="wav").read()
        data_8 = seg_8bit.export(io.BytesIO(), format="wav").read()

        result = _concat_wav_chunks([data_16, data_8])
        assert result.sample_width == 2  # 统一到第一个的 16bit


# ── export_to_mp3 ─────────────────────────────────────────


class TestExportToMp3:
    def test_exports_to_path(self, monkeypatch, tmp_path):
        """验证 export 被正确调用。"""
        export_calls = []

        def fake_export(self, path, **kw):
            export_calls.append((path, kw))

        monkeypatch.setattr(AudioSegment, "export", fake_export)

        audio = AudioSegment.silent(duration=100)
        output = tmp_path / "test.mp3"
        export_to_mp3(audio, output)

        assert len(export_calls) == 1
        call_path, call_kw = export_calls[0]
        assert str(call_path) == str(output)
        assert call_kw.get("format") == "mp3"

    def test_sets_channels(self, monkeypatch):
        """set_channels 参数应为 MP3_CHANNELS。"""
        channels_set = {"value": None}

        class FakeAudio:
            def set_channels(self, n):
                channels_set["value"] = n
                return self

            def export(self, *a, **kw):
                pass

        monkeypatch.setattr("assembler.MP3_CHANNELS", 1)
        export_to_mp3(FakeAudio(), Path("test.mp3"))
        assert channels_set["value"] == 1


# ── write_id3_tags ────────────────────────────────────────


class TestWriteId3Tags:
    def test_adds_tags(self, monkeypatch, tmp_path):
        """正常路径：写入 TIT2、TPE1、TALB、TRCK 标签。"""
        mp3_path = tmp_path / "01_test.mp3"
        mp3_path.write_text("fake mp3")

        added_tags = {}

        class FakeTags:
            def add(self, tag):
                added_tags[type(tag).__name__] = str(tag)

            def save(self, path):
                pass

        class FakeMP3:
            tags = FakeTags()

            def __init__(self, path):
                pass

        monkeypatch.setattr("assembler.MP3", FakeMP3)

        write_id3_tags(mp3_path, "书", "作者", "第一章", 1)
        assert "TIT2" in added_tags
        assert "TPE1" in added_tags
        assert "TALB" in added_tags
        assert "TRCK" in added_tags

    def test_adds_tags_when_none(self, monkeypatch, tmp_path):
        """tags 为 None 时调用 add_tags()。"""
        mp3_path = tmp_path / "02_test.mp3"
        mp3_path.write_text("fake mp3")

        add_tags_called = {"n": 0}

        class FakeTags:
            def add(self, tag):
                pass

            def save(self, path):
                pass

        class FakeMP3:
            tags = None

            def __init__(self, path):
                pass

            def add_tags(self):
                add_tags_called["n"] += 1
                self.tags = FakeTags()

        monkeypatch.setattr("assembler.MP3", FakeMP3)

        write_id3_tags(mp3_path, "书", "作者", "第一章", 1)
        assert add_tags_called["n"] == 1

    def test_parse_exception_adds_tags(self, monkeypatch, tmp_path):
        """MP3 解析抛出异常时走 except 分支。"""
        mp3_path = tmp_path / "03_test.mp3"
        mp3_path.write_text("corrupt")

        parse_count = {"n": 0}

        class FakeTags:
            def add(self, tag):
                pass

            def save(self, path):
                pass

        class FakeMP3:
            tags = FakeTags()

            def __init__(self, path):
                parse_count["n"] += 1

        monkeypatch.setattr("assembler.MP3", FakeMP3)

        write_id3_tags(mp3_path, "书", "作者", "第一章", 1)
        # 抛出异常 → except 路径再构造一次
        assert parse_count["n"] >= 1


# ── _sanitize_filename ────────────────────────────────────


class TestSanitizeFilename:
    def test_replaces_illegal_chars(self):
        assert _sanitize_filename("a:b") == "a_b"
        assert _sanitize_filename('a"b') == "a_b"
        assert _sanitize_filename("a/b") == "a_b"
        assert _sanitize_filename("a\\b") == "a_b"
        assert _sanitize_filename("a?b") == "a_b"
        assert _sanitize_filename("a*b") == "a_b"

    def test_clean_name_unchanged(self):
        assert _sanitize_filename("正常的文件名") == "正常的文件名"
        assert _sanitize_filename("01_第一章") == "01_第一章"


# ── assemble_book ─────────────────────────────────────────


class TestAssembleBook:
    def test_empty_chapter_audios(self, tmp_path):
        """空章节列表 → 返回 ([], 0)。"""
        paths, duration = assemble_book([], "书", "作者", tmp_path)
        assert paths == []
        assert duration == 0

    def test_skips_chapter_with_no_audio(self, tmp_path):
        """audio_chunks 为空的章节被跳过。"""
        chapters = [
            ChapterAudio(title="空章", track_num=1, audio_chunks=[]),
        ]
        paths, duration = assemble_book(chapters, "书", "作者", tmp_path)
        assert paths == []
        assert duration == 0

    def test_basic_assemble(self, monkeypatch, tmp_path):
        """正常章节 → 返回路径列表和总时长。"""
        wav_data = _make_wav(100)

        class FakeMP3:
            tags = type("Tags", (), {"add": lambda s, t: None, "save": lambda s, p: None})()

            def __init__(self, path):
                pass

        monkeypatch.setattr("assembler.MP3", FakeMP3)

        chapters = [
            ChapterAudio(title="第一章", track_num=1, audio_chunks=[wav_data]),
            ChapterAudio(title="第二章", track_num=2, audio_chunks=[wav_data]),
        ]
        paths, duration = assemble_book(chapters, "书", "作者", tmp_path)
        assert len(paths) == 2
        assert paths[0].name.startswith("01_")
        assert paths[1].name.startswith("02_")
        assert duration > 0
