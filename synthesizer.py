"""MiMo-V2.5-TTS 并发语音合成。"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from config import (
    MAX_RETRIES,
    MIMO_API_KEY,
    MIMO_BASE_URL,
    MIMO_TTS_MODEL,
    RETRY_BASE_DELAY,
    TTS_AUDIO_FORMAT,
    TTS_CONCURRENCY,
    TTS_STYLES,
    TTS_VOICES,
)
from cleaner import CleanedChapter

logger = logging.getLogger(__name__)


@dataclass
class ChapterAudio:
    title: str
    track_num: int
    audio_chunks: list[bytes]  # WAV bytes


async def synthesize_chapters(
    chapters: list[CleanedChapter],
    language: str = "zh",
    concurrency: int = TTS_CONCURRENCY,
) -> list[ChapterAudio]:
    """并发合成所有章节的音频。"""
    voice = TTS_VOICES.get(language, TTS_VOICES["zh"])
    style = TTS_STYLES.get(language, TTS_STYLES["zh"])
    logger.info(f"  TTS 音色: {voice}, 语言: {language}")

    client = AsyncOpenAI(api_key=MIMO_API_KEY, base_url=MIMO_BASE_URL)
    semaphore = asyncio.Semaphore(concurrency)

    async def _synthesize_chapter(
        idx: int, chapter: CleanedChapter
    ) -> ChapterAudio:
        tasks = [
            _synthesize_single(client, chunk, voice, style, semaphore)
            for chunk in chapter.chunks
        ]
        audio_chunks = await asyncio.gather(*tasks)
        return ChapterAudio(
            title=chapter.title,
            track_num=idx + 1,
            audio_chunks=[a for a in audio_chunks if a],
        )

    tasks = [_synthesize_chapter(idx, ch) for idx, ch in enumerate(chapters)]
    return await asyncio.gather(*tasks)


async def _synthesize_single(
    client: AsyncOpenAI,
    text: str,
    voice: str,
    style: str,
    semaphore: asyncio.Semaphore,
) -> bytes:
    """合成单个文本块，返回 WAV bytes。"""
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.chat.completions.create(
                    model=MIMO_TTS_MODEL,
                    messages=[
                        {"role": "user", "content": style},
                        {"role": "assistant", "content": text},
                    ],
                    audio={"format": TTS_AUDIO_FORMAT, "voice": voice},
                )
                message = response.choices[0].message
                if message.audio and message.audio.data:
                    return base64.b64decode(message.audio.data)
                logger.warning("TTS 返回空音频")
                return b""
            except Exception as e:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"TTS 失败 (attempt {attempt + 1}): {e}, {delay}s 后重试")
                await asyncio.sleep(delay)

        logger.error(f"TTS 最终失败: {text[:50]}...")
        return b""
