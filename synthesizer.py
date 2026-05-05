"""MiMo-V2.5-TTS 并发语音合成。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from openai import AsyncOpenAI
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

import config
from config import (
    MAX_RETRIES,
    MIMO_API_KEY,
    MIMO_BASE_URL,
    MIMO_TTS_MODEL,
    RETRY_BASE_DELAY,
    TTS_AUDIO_FORMAT,
    TTS_CACHE_DIR,
    TTS_CONCURRENCY,
)
from models import ChapterAudio, CleanedChapter
from text_processor import optimize_for_speech

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class SynthesisStats:
    total_chunks: int
    cache_hits: int
    api_calls: int
    failed_chunks: int


def _compute_cache_key(voice: str, style: str, processed_text: str) -> str:
    """计算 TTS 缓存键。

    Why: 缓存命中必须与生成参数完全对应，否则切换风格/音色/模型时会拿到错误音频。
    Key 因子：TTS 模型 + 音色 + 风格描述 + 预处理后的文本。
    """
    payload = f"{MIMO_TTS_MODEL}:{voice}:{style}:{processed_text}"
    return hashlib.md5(payload.encode()).hexdigest()


async def synthesize_chapters(
    chapters: list[CleanedChapter],
    language: str = "zh",
    concurrency: int = TTS_CONCURRENCY,
) -> tuple[list[ChapterAudio], SynthesisStats]:
    """并发合成所有章节的音频。返回 (音频列表, 统计信息)。"""
    voice = config.TTS_VOICES.get(language, config.TTS_VOICES["zh"])
    style = config.TTS_STYLES.get(language, config.TTS_STYLES["zh"])
    total_chunks = sum(len(ch.chunks) for ch in chapters)
    logger.info(f"  TTS 音色: {voice}, 语言: {language}")

    semaphore = asyncio.Semaphore(concurrency)

    cache_hits = 0
    api_calls = 0
    failed_chunks = 0

    def _fmt_time(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}:{int(seconds % 60):02d}"
        else:
            return f"{int(seconds // 3600)}:{int((seconds % 3600) // 60):02d}:{int(seconds % 60):02d}"

    progress = Progress(
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(complete_style="green", finished_style="green"),
        TaskProgressColumn(),
        TextColumn("[yellow]速度 {task.fields[speed]:.1f}块/s"),
        TextColumn("[dim]已用 {task.fields[elapsed_str]}"),
        TextColumn("[dim]剩余 {task.fields[remaining_str]}"),
        TextColumn("[blue]缓存{task.fields[cache_hits]}[/blue] [red]API{task.fields[api_calls]}[/red]"),
        console=console,
        transient=True,
    )

    async with AsyncOpenAI(api_key=MIMO_API_KEY, base_url=MIMO_BASE_URL) as client:
        with progress:
            task = progress.add_task(
                f"TTS 合成 ({len(chapters)} 章)",
                total=total_chunks,
                cache_hits=0,
                api_calls=0,
                speed=0.0,
                elapsed_str="0s",
                remaining_str="...",
            )

            async def _synthesize_chapter(
                idx: int, chapter: CleanedChapter
            ) -> ChapterAudio:
                nonlocal cache_hits, api_calls, failed_chunks

                async def _track_progress(chunk: str) -> bytes:
                    nonlocal cache_hits, api_calls, failed_chunks
                    processed = optimize_for_speech(chunk)
                    chunk_hash = _compute_cache_key(voice, style, processed)
                    cache_path = TTS_CACHE_DIR / f"{chunk_hash}.wav"
                    is_cached = cache_path.exists()

                    result = await _synthesize_single(client, chunk, voice, style, semaphore)

                    if is_cached:
                        cache_hits += 1
                    else:
                        api_calls += 1
                    if not result:
                        failed_chunks += 1

                    elapsed = progress.tasks[task].elapsed or 0
                    remaining = progress.tasks[task].remaining or 0
                    speed = progress.tasks[task].completed / max(elapsed, 1e-6)
                    progress.update(
                        task,
                        advance=1,
                        cache_hits=cache_hits,
                        api_calls=api_calls,
                        speed=speed,
                        elapsed_str=_fmt_time(elapsed),
                        remaining_str=_fmt_time(remaining) if remaining else "...",
                    )
                    return result

                tasks = [_track_progress(chunk) for chunk in chapter.chunks]
                audio_chunks = await asyncio.gather(*tasks)
                return ChapterAudio(
                    title=chapter.title,
                    track_num=idx + 1,
                    audio_chunks=[a for a in audio_chunks if a],
                )

            tasks = [_synthesize_chapter(idx, ch) for idx, ch in enumerate(chapters)]
            results = await asyncio.gather(*tasks)

        stats = SynthesisStats(
            total_chunks=total_chunks,
            cache_hits=cache_hits,
            api_calls=api_calls,
            failed_chunks=failed_chunks,
        )
        return results, stats


async def _synthesize_single(
    client: AsyncOpenAI,
    text: str,
    voice: str,
    style: str,
    semaphore: asyncio.Semaphore,
) -> bytes:
    """合成单个文本块，返回 WAV bytes。支持缓存。"""
    # 文本预处理（优化气口和停顿）
    processed_text = optimize_for_speech(text)

    # 检查缓存（key 包含 model+voice+style+文本，避免切风格/音色时读到错误音频）
    chunk_hash = _compute_cache_key(voice, style, processed_text)
    cache_path = TTS_CACHE_DIR / f"{chunk_hash}.wav"

    if cache_path.exists():
        # 不打印逐块日志：rich.Progress 已显示缓存命中数，logger 写 stderr 会打断进度条
        return cache_path.read_bytes()

    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.chat.completions.create(
                    model=MIMO_TTS_MODEL,
                    messages=[
                        {"role": "user", "content": style},
                        {"role": "assistant", "content": processed_text},
                    ],
                    audio={"format": TTS_AUDIO_FORMAT, "voice": voice},
                )
                message = response.choices[0].message
                if message.audio and message.audio.data:
                    audio_data = base64.b64decode(message.audio.data)
                    # 保存到缓存
                    cache_path.write_bytes(audio_data)
                    return audio_data
                # 空音频视为可重试错误，而非直接返回静音
                raise RuntimeError("TTS 返回空音频")
            except Exception as e:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"TTS 失败 (attempt {attempt + 1}): {e}, {delay}s 后重试")
                await asyncio.sleep(delay)

        logger.error(f"TTS 最终失败: {processed_text[:50]}...")
        return b""
