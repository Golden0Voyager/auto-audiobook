"""LLM 智能清洗 — MiMo-V2.5-Pro 语义级文本预处理。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from config import (
    LLM_CONCURRENCY,
    MAX_RETRIES,
    MIMO_API_KEY,
    MIMO_BASE_URL,
    MIMO_LLM_MODEL,
    RETRY_BASE_DELAY,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个文本预处理专家，任务是将电子书文本转化为适合语音播报的流畅文本。

规则：
1. 移除所有 URL、邮箱地址
2. 移除复杂数据表格、图表描述
3. 移除参考文献编号（如 [1]、[2]）
4. 将书面语适当转化为口语化表达
5. 保持原文的核心含义和叙事逻辑不变
6. 不要添加任何解释或评论，只输出清洗后的文本
7. 如果原文已经是正常叙述文本，原样返回即可"""


@dataclass
class CleanedChapter:
    title: str
    chunks: list[str]


async def clean_chapters(
    chapters: list[tuple[str, list[str]]],
    concurrency: int = LLM_CONCURRENCY,
) -> list[CleanedChapter]:
    """批量清洗所有章节的文本块。

    Args:
        chapters: [(chapter_title, [chunk, ...]), ...]
        concurrency: 最大并发数
    """
    client = AsyncOpenAI(api_key=MIMO_API_KEY, base_url=MIMO_BASE_URL)
    semaphore = asyncio.Semaphore(concurrency)

    async def _clean_chapter(title: str, chunks: list[str]) -> CleanedChapter:
        tasks = [_clean_single(client, chunk, semaphore) for chunk in chunks]
        cleaned = await asyncio.gather(*tasks)
        return CleanedChapter(title=title, chunks=list(cleaned))

    tasks = [_clean_chapter(title, chunks) for title, chunks in chapters]
    return await asyncio.gather(*tasks)


async def _clean_single(
    client: AsyncOpenAI,
    chunk: str,
    semaphore: asyncio.Semaphore,
) -> str:
    """清洗单个文本块，带重试机制。"""
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.chat.completions.create(
                    model=MIMO_LLM_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": chunk},
                    ],
                    temperature=0.3,
                )
                result = response.choices[0].message.content
                return result.strip() if result else chunk
            except Exception as e:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"清洗失败 (attempt {attempt + 1}): {e}, {delay}s 后重试")
                await asyncio.sleep(delay)

        logger.error(f"清洗失败，使用原文: {chunk[:50]}...")
        return chunk
