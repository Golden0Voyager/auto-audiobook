"""pipeline.process_book mock 全流程测试 — 编排逻辑、缓存、增量、试听。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from models import BookData, Chapter, ChapterAudio, CleanedChapter
from pipeline import process_book
from synthesizer import SynthesisStats

# ── 测试数据 ──────────────────────────────────────────────

_BOOK = BookData(
    title="测试书",
    author="测试作者",
    language="zh",
    chapters=[
        Chapter(title="第一章", chunks=["这是第一段。", "这是第二段。"]),
        Chapter(title="第二章", chunks=["这是第三段。"]),
    ],
)

_CLEANED = [
    CleanedChapter(title="第一章", chunks=["这是第一段-清洗后。", "这是第二段-清洗后。"]),
    CleanedChapter(title="第二章", chunks=["这是第三段-清洗后。"]),
]

_AUDIOS = [
    ChapterAudio(title="第一章", track_num=1, audio_chunks=[b"audio1", b"audio2"]),
    ChapterAudio(title="第二章", track_num=2, audio_chunks=[b"audio3"]),
]

_STATS = SynthesisStats(total_chunks=3, cache_hits=1, api_calls=2, failed_chunks=0)


def _mock_async_return(val):
    """构造一个返回固定值的 async函数。"""
    async def inner(*a, **kw):
        return val
    return inner


class TestProcessBookFullFlow:
    """Mock 全链路，测试 process_book 的整体编排逻辑。"""

    def _setup_common_mocks(self, monkeypatch, tmp_path):
        """所有测试共享的 mock：基础依赖 + output dir。"""
        import config
        monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(config, "CLEAN_MODE", "llm")
        monkeypatch.setattr("pipeline.console.print", lambda *a, **kw: None)
        monkeypatch.setattr("shutil.copy2", lambda *a, **kw: None)
        monkeypatch.setattr("pipeline.parse_file", lambda p: _BOOK)
        monkeypatch.setattr("pipeline._load_cleaned_cache", lambda p: None)
        monkeypatch.setattr("pipeline._get_existing_chapters", lambda p: set())

    def test_full_flow(self, monkeypatch, tmp_path):
        """LLM 清洗完整链路：parse → LLM clean → TTS → assemble → copy。"""
        self._setup_common_mocks(monkeypatch, tmp_path)

        clean_called = {"n": 0}

        async def fake_clean(chapters):
            clean_called["n"] += 1
            return _CLEANED

        monkeypatch.setattr("pipeline.clean_chapters", fake_clean)
        monkeypatch.setattr("pipeline.synthesize_chapters",
                            _mock_async_return((_AUDIOS, _STATS)))
        monkeypatch.setattr("pipeline.assemble_book",
                            lambda *a: ([Path("01_第一章.mp3")], 5000))

        result = asyncio.run(process_book(tmp_path / "测试书.epub"))
        assert isinstance(result, Path)
        assert clean_called["n"] == 1

    def test_rule_clean_mode(self, monkeypatch, tmp_path):
        """规则清洗分支：parse → rule clean → TTS → assemble。"""
        self._setup_common_mocks(monkeypatch, tmp_path)
        import config
        monkeypatch.setattr(config, "CLEAN_MODE", "rule")

        rule_called = {"n": 0}

        def fake_rule_clean(chapters):
            rule_called["n"] += 1
            return _CLEANED

        monkeypatch.setattr("pipeline.rule_clean_chapters", fake_rule_clean)
        monkeypatch.setattr("pipeline.synthesize_chapters",
                            _mock_async_return((_AUDIOS, _STATS)))
        monkeypatch.setattr("pipeline.assemble_book",
                            lambda *a: ([Path("01_第一章.mp3")], 5000))

        result = asyncio.run(process_book(tmp_path / "测试书.epub"))
        assert isinstance(result, Path)
        assert rule_called["n"] == 1

    def test_cache_hit(self, monkeypatch, tmp_path):
        """缓存命中时跳过 LLM/规则清洗，直接从缓存恢复。"""
        self._setup_common_mocks(monkeypatch, tmp_path)

        monkeypatch.setattr(
            "pipeline._load_cleaned_cache",
            lambda p: ("缓存书", "缓存作者", "zh", _CLEANED),
        )

        clean_called = {"n": 0}

        async def fake_clean(chapters):
            clean_called["n"] += 1
            return _CLEANED

        monkeypatch.setattr("pipeline.clean_chapters", fake_clean)
        monkeypatch.setattr("pipeline.synthesize_chapters",
                            _mock_async_return((_AUDIOS, _STATS)))
        monkeypatch.setattr("pipeline.assemble_book",
                            lambda *a: ([Path("01_第一章.mp3")], 5000))

        asyncio.run(process_book(tmp_path / "测试书.epub"))
        assert clean_called["n"] == 0  # 未调用清洗

    def test_preview_mode(self, monkeypatch, tmp_path):
        """试听模式：只处理前 N 个文本块。"""
        self._setup_common_mocks(monkeypatch, tmp_path)

        cleaned_tracked = {"chunks": 0}

        async def fake_synthesize(chapters, **kw):
            cleaned_tracked["chunks"] = sum(len(ch.chunks) for ch in chapters)
            audios = [
                ChapterAudio(title=ch.title, track_num=i + 1,
                             audio_chunks=[b"a" for _ in ch.chunks])
                for i, ch in enumerate(chapters)
            ]
            return (audios, SynthesisStats(
                total_chunks=cleaned_tracked["chunks"], cache_hits=0,
                api_calls=cleaned_tracked["chunks"], failed_chunks=0))

        monkeypatch.setattr("pipeline.clean_chapters",
                            _mock_async_return(_CLEANED))
        monkeypatch.setattr("pipeline.synthesize_chapters", fake_synthesize)
        monkeypatch.setattr("pipeline.assemble_book",
                            lambda *a: ([Path("01_第一章.mp3")], 1000))

        asyncio.run(process_book(tmp_path / "测试书.epub", preview_chunks=1))
        # _CLEANED 有 3 chunks total, preview=1 → 截取为 1 chunk
        assert cleaned_tracked["chunks"] == 1


class TestProcessBookIncremental:
    """增量处理：已存在的章节跳过 TTS。"""

    def test_incremental_skips_existing(self, monkeypatch, tmp_path):
        """章节 1 已存在，只合成章节 2。"""
        import config
        monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(config, "CLEAN_MODE", "llm")
        monkeypatch.setattr("pipeline.console.print", lambda *a, **kw: None)
        monkeypatch.setattr("shutil.copy2", lambda *a, **kw: None)
        monkeypatch.setattr("pipeline.parse_file", lambda p: _BOOK)
        monkeypatch.setattr("pipeline._load_cleaned_cache", lambda p: None)
        monkeypatch.setattr("pipeline.clean_chapters",
                            _mock_async_return(_CLEANED))
        # 章节 1 已存在
        monkeypatch.setattr("pipeline._get_existing_chapters", lambda p: {1})

        synthesized = {"chapters": []}

        async def fake_synthesize(chapters, **kw):
            synthesized["chapters"] = [(i, ch.title) for i, ch in enumerate(chapters)]
            audios = [
                ChapterAudio(title=ch.title, track_num=i + 1,
                             audio_chunks=[b"audio"])
                for i, ch in enumerate(chapters)
            ]
            return (audios, SynthesisStats(
                total_chunks=sum(len(ch.chunks) for ch in chapters),
                cache_hits=0, api_calls=1, failed_chunks=0))

        monkeypatch.setattr("pipeline.synthesize_chapters", fake_synthesize)
        monkeypatch.setattr("pipeline.assemble_book",
                            lambda *a: ([Path("02_第二章.mp3")], 2000))

        asyncio.run(process_book(tmp_path / "测试书.epub"))

        # 只有第二个章节被合成
        assert len(synthesized["chapters"]) == 1
        # 传递给 TTS 的章节经过 track_num 恢复
        # 注意：回调验证的是传递给 synthesize_chapters 的原始索引
        assert synthesized["chapters"][0][1] == "第二章"

    def test_all_chapters_existing(self, monkeypatch, tmp_path):
        """所有章节已处理完成，跳过 TTS + assemble，回退检测已有 MP3。"""
        import config
        monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(config, "CLEAN_MODE", "llm")
        monkeypatch.setattr("pipeline.console.print", lambda *a, **kw: None)
        monkeypatch.setattr("shutil.copy2", lambda *a, **kw: None)
        monkeypatch.setattr("pipeline.parse_file", lambda p: _BOOK)
        monkeypatch.setattr("pipeline._load_cleaned_cache", lambda p: None)
        monkeypatch.setattr("pipeline.clean_chapters",
                            _mock_async_return(_CLEANED))
        # 所有章节都已存在
        monkeypatch.setattr("pipeline._get_existing_chapters", lambda p: {1, 2})

        # 预先创建一些 MP3 文件用于回退检测
        output_dir = tmp_path / "测试书"
        output_dir.mkdir(parents=True)
        (output_dir / "01_第一章.mp3").write_text("fake mp3 1")
        (output_dir / "02_第二章.mp3").write_text("fake mp3 2")

        # Mock MP3 让回退扫描成功
        class FakeMP3Info:
            length = 100.0

        class FakeMP3:
            info = FakeMP3Info()
            def __init__(self, _path):
                pass

        monkeypatch.setattr("pipeline.MP3", FakeMP3)

        synthesize_called = {"n": 0}

        async def fake_synthesize(*a, **kw):
            synthesize_called["n"] += 1
            return ([], SynthesisStats(0, 0, 0, 0))

        assemble_called = {"n": 0}

        def fake_assemble(*a, **kw):
            assemble_called["n"] += 1
            return ([], 0)

        monkeypatch.setattr("pipeline.synthesize_chapters", fake_synthesize)
        monkeypatch.setattr("pipeline.assemble_book", fake_assemble)

        result = asyncio.run(process_book(tmp_path / "测试书.epub"))
        assert isinstance(result, Path)
        # synthesize_chapters 仍会被调用（chapters_to_process 为空，函数提前返回）
        assert synthesize_called["n"] == 0
        # assemble_book 被调用但无章节传给它的数据实际为空
        assert assemble_called["n"] == 1


class TestProcessBookEdgeCases:
    """异常路径和边界情况。"""

    def test_empty_book(self, monkeypatch, tmp_path):
        """无章节的书籍不抛出异常。"""
        import config
        monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(config, "CLEAN_MODE", "llm")
        monkeypatch.setattr("pipeline.console.print", lambda *a, **kw: None)
        monkeypatch.setattr("shutil.copy2", lambda *a, **kw: None)
        monkeypatch.setattr(
            "pipeline.parse_file",
            lambda p: BookData(title="空书", author="无", language="zh", chapters=[]),
        )
        monkeypatch.setattr("pipeline._load_cleaned_cache", lambda p: None)
        monkeypatch.setattr("pipeline._get_existing_chapters", lambda p: set())

        # 空章节 → clean_chapters 接收空列表
        clean_called = {"n": 0}

        async def fake_clean(chapters):
            clean_called["n"] += 1
            return []

        monkeypatch.setattr("pipeline.clean_chapters", fake_clean)
        monkeypatch.setattr(
            "pipeline.synthesize_chapters",
            _mock_async_return(([], SynthesisStats(0, 0, 0, 0))),
        )
        monkeypatch.setattr("pipeline.assemble_book",
                            lambda *a: ([], 0))

        result = asyncio.run(process_book(tmp_path / "空书.epub"))
        assert isinstance(result, Path)
