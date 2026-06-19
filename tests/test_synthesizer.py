"""synthesizer 单元测试 — 缓存键、单次合成、编排流程。"""

from __future__ import annotations

import asyncio
import base64
import hashlib

from models import CleanedChapter
from synthesizer import (
    _compute_cache_key,
    _synthesize_single,
    synthesize_chapters,
)


class TestComputeCacheKey:
    def test_different_voice_different_key(self):
        key1 = _compute_cache_key("茉莉", "default", "test")
        key2 = _compute_cache_key("苏打", "default", "test")
        assert key1 != key2

    def test_different_style_different_key(self):
        key1 = _compute_cache_key("茉莉", "default", "test")
        key2 = _compute_cache_key("茉莉", "news", "test")
        assert key1 != key2

    def test_different_text_different_key(self):
        key1 = _compute_cache_key("茉莉", "default", "test a")
        key2 = _compute_cache_key("茉莉", "default", "test b")
        assert key1 != key2

    def test_same_input_same_key(self):
        key1 = _compute_cache_key("茉莉", "default", "test")
        key2 = _compute_cache_key("茉莉", "default", "test")
        assert key1 == key2

    def test_deterministic_md5_format(self):
        key = _compute_cache_key("茉莉", "default", "test")
        assert len(key) == 32  # MD5 hexdigest
        assert all(c in "0123456789abcdef" for c in key)


class TestSynthesizeSingle:
    """测试 _synthesize_single 的缓存命中/未命中/重试逻辑。"""

    async def _make_fake_wav(self) -> bytes:
        """构造最小可解码 WAV。"""
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"\x00\x00" * 100)
        return buf.getvalue()

    async def test_cache_hit_returns_cached_bytes(self, monkeypatch, tmp_path):
        """缓存命中时直接读取缓存文件返回。"""
        monkeypatch.setattr("synthesizer.TTS_CACHE_DIR", tmp_path)

        fake_wav = await self._make_fake_wav()
        # 预先写入缓存
        hash_val = hashlib.md5(b"test").hexdigest()
        cached_path = tmp_path / f"{hash_val}.wav"
        cached_path.write_bytes(fake_wav)

        # Mock _compute_cache_key to return predictable hash
        monkeypatch.setattr(
            "synthesizer._compute_cache_key",
            lambda v, s, t: hashlib.md5(b"test").hexdigest(),
        )

        client = None  # 缓存命中时不需要 client
        result = await _synthesize_single(client, "hello", "茉莉", "default", asyncio.Semaphore(1))
        assert result == fake_wav

    async def test_cache_miss_calls_api_and_saves_cache(self, monkeypatch, tmp_path):
        """缓存未命中时调 API 并保存结果到缓存。"""
        monkeypatch.setattr("synthesizer.TTS_CACHE_DIR", tmp_path)

        fake_wav = await self._make_fake_wav()
        fake_b64 = base64.b64encode(fake_wav).decode()

        call_count = {"n": 0}

        class FakeChoice:
            message = type("Msg", (), {"audio": type("Aud", (), {"data": fake_b64})})()

        class FakeResponse:
            choices = [FakeChoice()]

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    async def create(**kw):
                        call_count["n"] += 1
                        return FakeResponse()

        monkeypatch.setattr(
            "synthesizer._compute_cache_key",
            lambda v, s, t: "testhash",
        )

        result = await _synthesize_single(FakeClient(), "hello", "茉莉", "default", asyncio.Semaphore(1))
        assert result == fake_wav
        assert call_count["n"] == 1
        # 缓存文件被创建
        assert (tmp_path / "testhash.wav").exists()

    async def test_empty_audio_triggers_retry_then_returns_empty(self, monkeypatch, tmp_path):
        """API 返回空音频 → 重试 → 最终返回空 bytes。"""
        monkeypatch.setattr("synthesizer.TTS_CACHE_DIR", tmp_path)
        monkeypatch.setattr("synthesizer.MAX_RETRIES", 2)
        monkeypatch.setattr("synthesizer.RETRY_BASE_DELAY", 0.01)

        class FakeChoice:
            message = type("Msg", (), {"audio": None})()

        class FakeResponse:
            choices = [FakeChoice()]

        call_count = {"n": 0}

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    async def create(**kw):
                        call_count["n"] += 1
                        return FakeResponse()

        monkeypatch.setattr(
            "synthesizer._compute_cache_key",
            lambda v, s, t: "empty_hash",
        )

        result = await _synthesize_single(FakeClient(), "hello", "茉莉", "default", asyncio.Semaphore(1))
        assert result == b""
        assert call_count["n"] == 2  # 重试了

    async def test_all_retries_fail_returns_empty(self, monkeypatch, tmp_path):
        """所有重试都失败时返回空 bytes。"""
        monkeypatch.setattr("synthesizer.TTS_CACHE_DIR", tmp_path)
        monkeypatch.setattr("synthesizer.MAX_RETRIES", 2)
        monkeypatch.setattr("synthesizer.RETRY_BASE_DELAY", 0.01)

        call_count = {"n": 0}

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    async def create(**kw):
                        call_count["n"] += 1
                        raise RuntimeError("API timeout")

        monkeypatch.setattr(
            "synthesizer._compute_cache_key",
            lambda v, s, t: "fail_hash",
        )

        result = await _synthesize_single(FakeClient(), "hello", "茉莉", "default", asyncio.Semaphore(1))
        assert result == b""
        assert call_count["n"] == 2


class TestSynthesizeChapters:
    """测试 synthesize_chapters 编排逻辑（mock 内部函数）。"""

    async def test_empty_chapters(self):
        """空章节列表返回空结果。"""
        results, stats = await synthesize_chapters([], language="zh")
        assert results == []
        assert stats.total_chunks == 0

    async def test_basic_flow(self, monkeypatch, tmp_path):
        """基本流程：合成一个章节，检查结果结构。"""
        import config
        monkeypatch.setattr(config, "TTS_CACHE_DIR", tmp_path)
        monkeypatch.setattr(config, "TTS_VOICES", {"zh": "茉莉"})
        monkeypatch.setattr(config, "TTS_STYLES", {"zh": "default style"})

        # Mock _synthesize_single to return fake audio
        fake_wav = b"FAKE_AUDIO_DATA"

        async def fake_synthesize(client, text, voice, style, sem):
            return fake_wav

        monkeypatch.setattr("synthesizer._synthesize_single", fake_synthesize)

        chapters = [
            CleanedChapter(title="第一章", chunks=["文本块1", "文本块2"]),
        ]
        results, stats = await synthesize_chapters(chapters, language="zh")

        assert len(results) == 1
        assert results[0].title == "第一章"
        assert len(results[0].audio_chunks) == 2
        assert results[0].audio_chunks[0] == fake_wav
        assert stats.total_chunks == 2

    async def test_stats_tracking(self, monkeypatch, tmp_path):
        """验证统计信息正确跟踪缓存命中、API 调用和失败。"""
        import config
        monkeypatch.setattr(config, "TTS_CACHE_DIR", tmp_path)
        monkeypatch.setattr(config, "TTS_VOICES", {"zh": "茉莉"})
        monkeypatch.setattr(config, "TTS_STYLES", {"zh": "default style"})

        call_count = {"n": 0}

        async def fake_synthesize(client, text, voice, style, sem):
            call_count["n"] += 1
            if call_count["n"] % 2 == 0:
                return b""  # 偶数调用返回空音频（失败）
            return b"FAKE_AUDIO"

        monkeypatch.setattr("synthesizer._synthesize_single", fake_synthesize)

        chapters = [CleanedChapter(title="第1章", chunks=["a", "b", "c"])]
        results, stats = await synthesize_chapters(chapters, language="zh")

        assert stats.total_chunks == 3
        # 只有奇数调用成功，偶数失败
        assert len(results[0].audio_chunks) == 2  # 成功的有 2 个
        assert stats.failed_chunks == 1
