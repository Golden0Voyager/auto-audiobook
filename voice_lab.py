"""试听对比室 — 批量合成多组合，让用户横向比较音色与风格。"""
from __future__ import annotations

import re

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
