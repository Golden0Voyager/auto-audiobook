"""voice_lab 单元/集成测试。"""
import random

import pytest

from models import BookData, Chapter
from voice_lab import _sample_preview_text, _truncate_at_sentence


def _make_book(chapters: list[tuple[str, list[str]]]) -> BookData:
    return BookData(
        title="t",
        author="a",
        language="zh",
        chapters=[Chapter(title=t, chunks=cs) for t, cs in chapters],
    )


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


def test_sample_preview_text_filters_short_titles_and_short_chapters(monkeypatch):
    book = _make_book([
        ("目", ["x" * 50]),
        ("封面", ["short"]),
        ("第一章 旅程开始", ["正" * 600]),
        ("第二章 风暴", ["浪" * 600]),
    ])
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    out = _sample_preview_text(book, target_chars=100)
    assert out.startswith("正")


def test_sample_preview_text_falls_back_when_all_filtered(monkeypatch):
    book = _make_book([
        ("a", ["A" * 30]),
        ("b", ["B" * 30]),
    ])
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    out = _sample_preview_text(book, target_chars=200)
    assert out == "A" * 30


def test_sample_preview_text_pads_when_first_chunk_too_short(monkeypatch):
    book = _make_book([
        ("第一章 长正文", ["abc", "defghij" * 10]),
    ])
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    out = _sample_preview_text(book, target_chars=100)
    assert out.startswith("abc")
    assert len(out) >= 50


def test_sample_preview_text_does_not_mutate_book(monkeypatch):
    book = _make_book([
        ("第一章 长正文", ["abc", "d" * 100]),
    ])
    original_chunks = list(book.chapters[0].chunks)
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    _sample_preview_text(book, target_chars=200)
    assert book.chapters[0].chunks == original_chunks


def test_sample_preview_text_returns_empty_when_chunks_all_empty(monkeypatch):
    book = _make_book([
        ("第一章 标题够长但无内容", []),
        ("第二章 标题够长但无内容", []),
    ])
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    out = _sample_preview_text(book, target_chars=200)
    assert out == ""
