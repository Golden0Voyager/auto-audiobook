"""文本预处理 — 优化朗读效果，添加气口和停顿。"""

from __future__ import annotations

import re

# ── 预编译正则（避免每次调用重复编译，千次 chunk 处理时收益明显）──
_CHINESE_CHAR_RE = re.compile(r"[一-鿿]")
_ENGLISH_CHAR_RE = re.compile(r"[a-zA-Z]")
_DIGIT_CHAR_RE = re.compile(r"[0-9]")

_SENTENCE_SPACE_RE = re.compile(r"([。！？])\s*")

_PARA_COLLAPSE_RE = re.compile(r"\n\s*\n")

_PAUSE_WORDS = [
    "但是", "然而", "不过", "可是", "虽然", "尽管",
    "首先", "其次", "再次", "最后", "另外", "此外", "同时",
]
_PAUSE_WORDS_RE = re.compile(
    r"(?<![，。！？；\s\n])(" + "|".join(map(re.escape, _PAUSE_WORDS)) + ")"
)
_QUOTE_PAUSE_RE = re.compile(r'([^，。！？；\s\n])"')

_YEAR_RE = re.compile(r"(\d{4})年")
_PERCENT_RE = re.compile(r"(\d+)%")


def detect_language(text: str) -> tuple[str, float]:
    """检测文本主要语言，返回 (语言代码, 置信度)。

    Returns:
        tuple: ('zh' 或 'en', 置信度 0.0-1.0)
    """
    if not text or len(text.strip()) == 0:
        return "zh", 0.5  # 默认中文，低置信度

    # 取前 1000 字符进行检测（更准确）
    sample = text[:1000]
    total_chars = len(sample)

    # 统计中文字符（CJK 统一汉字）
    chinese_chars = len(_CHINESE_CHAR_RE.findall(sample))
    # 统计英文字符（字母）
    english_chars = len(_ENGLISH_CHAR_RE.findall(sample))
    # 统计数字
    digit_chars = len(_DIGIT_CHAR_RE.findall(sample))

    # 计算比例
    chinese_ratio = chinese_chars / total_chars if total_chars > 0 else 0
    english_ratio = english_chars / total_chars if total_chars > 0 else 0

    # 判断语言
    if chinese_ratio > 0.2:
        # 中文比例超过 20%，判定为中文
        confidence = min(chinese_ratio * 2, 1.0)  # 置信度
        return "zh", confidence
    elif english_ratio > 0.3:
        # 英文比例超过 30%，判定为英文
        confidence = min(english_ratio * 1.5, 1.0)
        return "en", confidence
    else:
        # 混合或无法判断，默认中文
        return "zh", 0.5


def get_language_name(lang_code: str) -> str:
    """获取语言的中文名称。"""
    return {"zh": "中文", "en": "英文"}.get(lang_code, "未知")


def optimize_for_speech(text: str) -> str:
    """优化文本以提升语音合成效果。

    处理内容：
    1. 规范化标点符号
    2. 添加适当的停顿
    3. 优化段落分隔
    4. 处理数字和特殊符号
    """
    text = _normalize_punctuation(text)
    text = _add_pauses(text)
    # _optimize_paragraphs 默认跳过：按逗号机械拆分会破坏语义连贯性（如"虽然…但是…"）
    # 如需启用可在此调用，但建议阈值 > 200 字
    # text = _optimize_paragraphs(text)
    text = _process_numbers(text)
    return text


def _normalize_punctuation(text: str) -> str:
    """规范化标点符号，确保 TTS 能正确识别。"""
    # 统一中文标点
    replacements = {
        ",,,": "，",
        "..": "。",
        "!!": "！",
        "??": "？",
        "...": "……",
        "--": "——",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # 确保句号后有空格（帮助 TTS 识别句子边界）
    text = _SENTENCE_SPACE_RE.sub(r"\1 ", text)

    return text.strip()


def _add_pauses(text: str) -> str:
    """在适当位置添加停顿标记。"""
    # 在段落之间添加较长停顿（用换行表示）
    text = _PARA_COLLAPSE_RE.sub("\n\n", text)

    # 在转折词/序列词前添加停顿（仅当前面不是标点符号时）
    # 单次正则扫描替代 O(k·n) 的循环替换
    text = _PAUSE_WORDS_RE.sub(r"，\1", text)

    # 在引号前添加短停顿（仅当前面不是标点符号时）
    text = _QUOTE_PAUSE_RE.sub(r"\1，\"", text)

    return text


def _optimize_paragraphs(text: str) -> str:
    """优化段落结构，避免过长句子。"""
    # 将超长句子按逗号分段
    sentences = text.split("。")
    optimized = []

    for sentence in sentences:
        if len(sentence) > 100:
            # 按逗号分段，每段不超过 50 字
            parts = sentence.split("，")
            buffer = ""
            for part in parts:
                if len(buffer) + len(part) < 50:
                    buffer += part + "，" if buffer else part
                else:
                    if buffer:
                        optimized.append(buffer.rstrip("，"))
                    buffer = part
            if buffer:
                optimized.append(buffer.rstrip("，"))
        else:
            optimized.append(sentence)

    return "。".join(optimized)


def _process_numbers(text: str) -> str:
    """处理数字，使其更适合朗读。"""
    # 年份：2026年 -> 二零二六年
    def _year_to_chinese(match: re.Match) -> str:
        year = match.group(1)
        chinese_digits = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四",
                         "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}
        result = "".join(chinese_digits.get(d, d) for d in year)
        return f"{result}年"

    text = _YEAR_RE.sub(_year_to_chinese, text)

    # 百分比：30% -> 百分之三十（仅转换合理范围内的百分比）
    def _percent_to_chinese(match: re.Match) -> str:
        num = int(match.group(1))
        if num > 9999:
            return match.group(0)  # 超大数字保留原样
        return f"百分之{_number_to_chinese(num)}"

    text = _PERCENT_RE.sub(_percent_to_chinese, text)

    return text


def _number_to_chinese(num: int) -> str:
    """将数字转换为中文读法。"""
    if num == 0:
        return "零"

    digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    units = ["", "十", "百", "千", "万", "十", "百", "千", "亿"]

    result = ""
    str_num = str(num)
    length = len(str_num)

    for i, digit in enumerate(str_num):
        idx = length - i - 1
        if digit != "0":
            if idx < len(units):
                result += digits[int(digit)] + units[idx]
            else:
                return str(num)  # 超出范围，直接返回数字字符串
        elif not result.endswith("零"):
            result += "零"

    return result.rstrip("零")
