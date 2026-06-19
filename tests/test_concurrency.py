"""并发性能测试 — 模拟不同并发度下的 TTS 吞吐量。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pytest


@dataclass
class SimulatedChapter:
    chunks: list[str]


async def _mock_tts_call(chunk: str, latency_ms: float = 200) -> bytes:
    """模拟一次 TTS API 调用（200ms 延迟）。"""
    await asyncio.sleep(latency_ms / 1000)
    return b"FAKE_AUDIO"


async def synthesize_with_concurrency(
    chapters: list[SimulatedChapter],
    concurrency: int,
    latency_ms: float = 200,
) -> float:
    """返回总耗时（秒）。"""
    semaphore = asyncio.Semaphore(concurrency)

    async def _process(chunk: str) -> bytes:
        async with semaphore:
            return await _mock_tts_call(chunk, latency_ms)

    start = time.perf_counter()
    tasks = []
    for ch in chapters:
        for chunk in ch.chunks:
            tasks.append(_process(chunk))
    await asyncio.gather(*tasks)
    return time.perf_counter() - start


class TestConcurrencyScaling:
    """验证并发度提升能否线性降低总耗时。"""

    @pytest.mark.parametrize("concurrency", [1, 5, 10, 25, 50, 100])
    def test_scaling(self, concurrency):
        """50 chunks × 200ms API 延迟，不同并发度下的耗时。"""
        chapters = [SimulatedChapter(chunks=[f"chunk{i}" for i in range(50)])]
        elapsed = asyncio.run(
            synthesize_with_concurrency(chapters, concurrency, latency_ms=50)
        )
        # 理论最短时间 = ceil(50 / concurrency) * 0.05s
        theoretical = (50 / concurrency) * 0.05
        # 允许 30% 的调度开销
        assert elapsed <= theoretical * 1.3 + 0.1
        print(f"  concurrency={concurrency:3d}: {elapsed:.3f}s (theoretical {theoretical:.3f}s)")

    def test_25_vs_50(self):
        """直接对比 25 和 50 并发。"""
        chapters = [SimulatedChapter(chunks=[f"c{i}" for i in range(100)])]
        t25 = asyncio.run(synthesize_with_concurrency(chapters, 25, latency_ms=50))
        t50 = asyncio.run(synthesize_with_concurrency(chapters, 50, latency_ms=50))
        print(f"\n  25并发: {t25:.3f}s")
        print(f"  50并发: {t50:.3f}s")
        print(f"  提速: {(t25 - t50) / t25 * 100:.1f}%")
        # 50 并发应该比 25 快至少 30%
        assert t50 < t25 * 0.8
