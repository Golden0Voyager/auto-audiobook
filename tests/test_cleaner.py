"""cleaner 单元测试 — 单次 LLM 清洗（mock）、批量编排、重试与回退。"""

from __future__ import annotations

import asyncio

from cleaner import _clean_single, clean_chapters


class TestCleanSingle:
    """测试 _clean_single 的 API 调用、重试和回退逻辑。"""

    async def test_success_returns_cleaned_text(self, monkeypatch):
        """正常调用返回清洗后的文本。"""
        call_count = {"n": 0}

        class FakeChoice:
            message = type("Msg", (), {"content": "清洗后的结果。", "strip": lambda s: "清洗后的结果。"})()

        class FakeResponse:
            choices = [FakeChoice()]

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    async def create(**kw):
                        call_count["n"] += 1
                        return FakeResponse()

        result = await _clean_single(FakeClient(), "原始文本", asyncio.Semaphore(1))
        assert result == "清洗后的结果。"
        assert call_count["n"] == 1

    async def test_empty_response_falls_back_to_original(self, monkeypatch):
        """API 返回空内容时回退到原文。"""
        class FakeChoice:
            message = type("Msg", (), {"content": None, "strip": lambda s: ""})()

        class FakeResponse:
            choices = [FakeChoice()]

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    async def create(**kw):
                        return FakeResponse()

        result = await _clean_single(FakeClient(), "原始文本", asyncio.Semaphore(1))
        assert result == "原始文本"

    async def test_retry_on_error_then_success(self, monkeypatch):
        """第一次调用失败，重试后成功。"""
        monkeypatch.setattr("cleaner.MAX_RETRIES", 3)
        monkeypatch.setattr("cleaner.RETRY_BASE_DELAY", 0.01)

        call_count = {"n": 0}

        class FakeChoice:
            message = type("Msg", (), {"content": "成功结果", "strip": lambda s: "成功结果"})()

        class FakeResponse:
            choices = [FakeChoice()]

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    async def create(**kw):
                        call_count["n"] += 1
                        if call_count["n"] == 1:
                            raise RuntimeError("API error")
                        return FakeResponse()

        result = await _clean_single(FakeClient(), "原始文本", asyncio.Semaphore(1))
        assert result == "成功结果"
        assert call_count["n"] == 2

    async def test_all_retries_fail_returns_original(self, monkeypatch):
        """所有重试都失败时回退到原文。"""
        monkeypatch.setattr("cleaner.MAX_RETRIES", 2)
        monkeypatch.setattr("cleaner.RETRY_BASE_DELAY", 0.01)

        call_count = {"n": 0}

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    async def create(**kw):
                        call_count["n"] += 1
                        raise RuntimeError("Persistent error")

        result = await _clean_single(FakeClient(), "原始文本", asyncio.Semaphore(1))
        assert result == "原始文本"
        assert call_count["n"] == 2


class TestCleanChapters:
    """测试 clean_chapters 批量编排（mock _clean_single）。"""

    async def test_empty_input(self):
        """空输入返回空列表。"""
        result = await clean_chapters([])
        assert result == []

    async def test_single_chapter_single_chunk(self, monkeypatch):
        """单章节单文本块的基本流程。"""
        async def fake_clean(client, chunk, sem):
            return f"清洗:{chunk}"

        monkeypatch.setattr("cleaner._clean_single", fake_clean)

        chapters = [("第一章", ["原始文本"])]
        result = await clean_chapters(chapters)
        assert len(result) == 1
        assert result[0].title == "第一章"
        assert result[0].chunks == ["清洗:原始文本"]

    async def test_multiple_chapters_and_chunks(self, monkeypatch):
        """多章节多文本块的结构一致性。"""
        async def fake_clean(client, chunk, sem):
            return f"cleaned_{chunk}"

        monkeypatch.setattr("cleaner._clean_single", fake_clean)

        chapters = [
            ("第1章", ["a", "b"]),
            ("第2章", ["c", "d", "e"]),
        ]
        result = await clean_chapters(chapters)
        assert len(result) == 2
        assert result[0].title == "第1章"
        assert result[0].chunks == ["cleaned_a", "cleaned_b"]
        assert result[1].title == "第2章"
        assert result[1].chunks == ["cleaned_c", "cleaned_d", "cleaned_e"]
