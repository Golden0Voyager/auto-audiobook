"""规则引擎文本清洗 — 零 API 调用，毫秒级处理。"""

from __future__ import annotations

import re

from models import CleanedChapter


def clean_chapters(
    chapters: list[tuple[str, list[str]]],
) -> list[CleanedChapter]:
    """批量清洗所有章节的文本块（规则引擎版本）。

    Args:
        chapters: [(chapter_title, [chunk, ...]), ...]
    """
    return [
        CleanedChapter(title=title, chunks=[_clean_chunk(c) for c in chunks])
        for title, chunks in chapters
    ]


def _clean_chunk(text: str) -> str:
    """清洗单个文本块。"""
    text = _remove_urls(text)
    text = _remove_emails(text)
    text = _remove_references(text)
    text = _remove_control_chars(text)
    text = _collapse_blank_lines(text)
    return text.strip()


def _remove_urls(text: str) -> str:
    """移除 URL。"""
    return re.sub(r"https?://\S+", "", text)


def _remove_emails(text: str) -> str:
    """移除邮箱地址。"""
    return re.sub(r"\b\w+@\w+\.\w+\b", "", text)


def _remove_references(text: str) -> str:
    """移除参考文献编号 [1] [2] 等。"""
    return re.sub(r"\[\d+\]", "", text)


def _remove_control_chars(text: str) -> str:
    """移除控制字符（保留换行和制表符）。"""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)


def _collapse_blank_lines(text: str) -> str:
    """合并连续空行为两个换行。"""
    return re.sub(r"\n{3,}", "\n\n", text)
