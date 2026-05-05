"""voice_lab 单元/集成测试。"""
from voice_lab import _truncate_at_sentence


def test_truncate_at_sentence_finds_chinese_period():
    text = "这是第一句话。这是第二句话。这是第三句话。这是第四句话。"
    out = _truncate_at_sentence(text, target=8)
    assert out == "这是第一句话。"


def test_truncate_at_sentence_returns_full_when_short():
    text = "短文本。"
    assert _truncate_at_sentence(text, target=200) == "短文本。"


def test_truncate_at_sentence_falls_back_to_hard_cut_when_no_punctuation():
    text = "abcdefghijklmnopqrstuvwxyz"
    assert _truncate_at_sentence(text, target=10) == "abcdefghij"


def test_truncate_at_sentence_handles_english_period():
    text = "This is sentence one. This is sentence two. This is sentence three."
    out = _truncate_at_sentence(text, target=25)
    assert out == "This is sentence one."
