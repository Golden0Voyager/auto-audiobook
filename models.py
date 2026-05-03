"""共享数据模型 — 避免模块间循环导入。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chapter:
    title: str
    chunks: list[str]


@dataclass
class BookData:
    title: str
    author: str
    language: str = "zh"  # "zh" or "en"
    chapters: list[Chapter] = field(default_factory=list)


@dataclass
class CleanedChapter:
    title: str
    chunks: list[str]


@dataclass
class ChapterAudio:
    title: str
    track_num: int
    audio_chunks: list[bytes]  # WAV bytes
