"""试听对比室 — 批量合成多组合，让用户横向比较音色与风格。"""
from __future__ import annotations

import random
import re

import questionary

import config
from models import BookData

_SENTENCE_END = re.compile(r'[。！？!?\.](?=[^"」』]|$)')


def _truncate_at_sentence(text: str, target: int) -> str:
    """在 [target*0.7, target*1.3] 区间内寻找最近句末标点截断。

    无合适标点时硬截断到 target。
    """
    if len(text) <= target:
        return text
    window = text[: int(target * 1.3)]
    cuts = [m.end() for m in _SENTENCE_END.finditer(window)]
    cuts = [c for c in cuts if c >= target * 0.7]
    if cuts:
        return text[: cuts[0]]
    return text[:target]


def _sample_preview_text(book: BookData, target_chars: int = 200) -> str:
    """从书中智能抽取一段试听文本。

    规则：
    1. 过滤"目录式"章节（标题<=2字 或 章节总文本<=200字）
    2. 全部被过滤则回退到原始章节列表
    3. 随机选一章；最多重抽 3 次以避开 chunks 为空的章节
    4. 取首个 chunk 在自然边界截断到 ~target_chars
    5. 不足 50 字时,拼接同章后续 chunk（不修改原对象）
    """
    content_chapters = [
        ch for ch in book.chapters
        if len(ch.title) > 2 and sum(len(c) for c in ch.chunks) > 200
    ]
    if not content_chapters:
        content_chapters = book.chapters

    chapter = None
    for _ in range(3):
        candidate = random.choice(content_chapters)
        if candidate.chunks:
            chapter = candidate
            break
    if chapter is None:
        return ""

    text = _truncate_at_sentence(chapter.chunks[0], target_chars)

    idx = 1
    while len(text) < 50 and idx < len(chapter.chunks):
        text += chapter.chunks[idx][: target_chars - len(text)]
        idx += 1
    return text


# 与 main.py 的 STYLE_LABELS 同步；voice_lab 独立声明避免循环依赖
_STYLE_LABELS_ZH = {
    "default": "默认（平静温暖）",
    "news": "新闻播报（权威专业）",
    "story": "故事叙述（富有感情）",
    "biography": "传记叙述（客观平实）",
    "nonfiction": "知识讲解（清晰逻辑）",
}
_STYLE_LABELS_EN = {
    "default": "Default (calm & warm)",
    "news": "News (authoritative)",
    "story": "Story (emotional)",
    "biography": "Biography (objective)",
    "nonfiction": "Non-fiction (clear logic)",
}


def _style_labels(language: str) -> dict[str, str]:
    return _STYLE_LABELS_EN if language == "en" else _STYLE_LABELS_ZH


def _select_combos(language: str) -> list[tuple[str, str]]:
    """让用户勾选 (voice, style) 组合。返回选定的列表。

    默认勾选：当前语言下所有音色 × 'default' 风格。
    超 20 个时弹 confirm 防误操作（软提示，不强阻断）。
    """
    voices = config.TTS_VOICE_OPTIONS.get(language, config.TTS_VOICE_OPTIONS["zh"])
    styles = _style_labels(language)

    choices = []
    for v in voices:
        for style_key, style_label in styles.items():
            title = f"{v['name']} × {style_label}"
            checked = (style_key == "default")
            choices.append(
                questionary.Choice(
                    title=title,
                    value=(v["name"], style_key),
                    checked=checked,
                )
            )

    selected = questionary.checkbox(
        "勾选要试听的 (音色 × 风格) 组合（空格选/取消，回车确认）：",
        choices=choices,
    ).ask() or []

    if len(selected) > 20:
        ok = questionary.confirm(
            f"勾选 {len(selected)} 个组合，预计耗时 ~{len(selected) * 3} 秒，确认？",
            default=True,
        ).ask()
        if not ok:
            return []

    return list(selected)


