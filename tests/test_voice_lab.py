"""voice_lab 单元/集成测试。"""
import random

import voice_lab as vl_module
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


async def test_select_combos_default_includes_all_voices_with_default_style(monkeypatch):
    """默认勾选 = 当前语言下所有音色 × 'default' 风格。"""
    captured = {}

    class _FakeCheckbox:
        def __init__(self, _msg, choices, **kw):
            captured["choices"] = choices

        async def unsafe_ask_async(self):
            return [c.value for c in captured["choices"] if c.checked]

    class _FakeConfirm:
        def __init__(self, _msg, default=True):
            self.default = default

        async def unsafe_ask_async(self):
            return True

    monkeypatch.setattr(vl_module.questionary, "checkbox", _FakeCheckbox)
    monkeypatch.setattr(vl_module.questionary, "confirm", _FakeConfirm)

    combos = await vl_module._select_combos("zh")

    assert len(combos) == 4
    assert all(style == "default" for _, style in combos)
    voice_names = {v for v, _ in combos}
    assert voice_names == {"茉莉", "白桦", "苏打", "冰糖"}


async def test_select_combos_warns_when_over_twenty(monkeypatch):
    """超 20 个组合时应弹 confirm。"""
    confirm_calls = []

    class _FakeCheckbox:
        def __init__(self, _msg, choices, **kw):
            self._choices = choices

        async def unsafe_ask_async(self):
            return [c.value for c in self._choices]

    class _FakeConfirm:
        def __init__(self, _msg, default=True):
            confirm_calls.append(_msg)

        async def unsafe_ask_async(self):
            return True

    monkeypatch.setattr(vl_module.questionary, "checkbox", _FakeCheckbox)
    monkeypatch.setattr(vl_module.questionary, "confirm", _FakeConfirm)

    import config
    original = list(config.TTS_VOICE_OPTIONS["zh"])
    monkeypatch.setattr(
        config,
        "TTS_VOICE_OPTIONS",
        {**config.TTS_VOICE_OPTIONS,
         "zh": original + [{"name": "测试音", "gender": "female", "label": "test"}]},
    )

    combos = await vl_module._select_combos("zh")
    assert len(combos) == 25
    assert any("勾选" in msg or "组合" in msg for msg in confirm_calls)


def _minimal_wav_bytes() -> bytes:
    """构造最小可解码的 WAV：标准头 + 几个采样点静音。"""
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 100)
    return buf.getvalue()


async def test_synthesize_previews_partial_failure(monkeypatch, tmp_path):
    """一个组合 raise，其他组合应正常返回。"""
    from models import ChapterAudio
    from voice_lab import _synthesize_previews

    call_count = {"n": 0}

    async def fake_synthesize_chapters(chapters, language="zh"):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated TTS failure")
        wav_bytes = _minimal_wav_bytes()
        return [ChapterAudio(title=chapters[0].title, track_num=1, audio_chunks=[wav_bytes])], None

    monkeypatch.setattr(vl_module, "synthesize_chapters", fake_synthesize_chapters)

    combos = [("茉莉", "default"), ("白桦", "default"), ("苏打", "default")]
    items = await _synthesize_previews("测试文本。", "zh", combos, tmp_path)

    assert len(items) == 3
    successes = [it for it in items if it.error is None]
    failures = [it for it in items if it.error is not None]
    assert len(successes) == 2
    assert len(failures) == 1
    assert failures[0].voice == "白桦"
    assert "simulated" in failures[0].error
    for it in successes:
        assert it.mp3_path and it.mp3_path.exists()
