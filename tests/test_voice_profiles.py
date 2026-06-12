"""voice_profiles 单元测试 — 音色查询和 profiles 显示。"""

from __future__ import annotations

from voice_profiles import (
    CATEGORY_LABELS,
    VOICE_PROFILES,
    display_voice_profiles,
    get_voice_description,
    get_voice_names,
)


class TestGetVoiceNames:
    def test_returns_names_for_known_category(self):
        names = get_voice_names("magazine", "zh")
        assert "mature_male" in names
        assert "warm_female" in names

    def test_returns_empty_for_unknown_category(self):
        assert get_voice_names("nonexistent", "zh") == []

    def test_returns_empty_for_unknown_language(self):
        assert get_voice_names("magazine", "fr") == []


class TestGetVoiceDescription:
    def test_returns_description_for_known_voice(self):
        desc = get_voice_description("magazine", "zh", "mature_male")
        assert isinstance(desc, str)
        assert len(desc) > 20

    def test_returns_empty_for_unknown_voice(self):
        assert get_voice_description("magazine", "zh", "ghost") == ""

    def test_returns_empty_for_unknown_category(self):
        assert get_voice_description("nope", "zh", "mature_male") == ""


class TestCategoryLabels:
    def test_all_categories_have_labels(self):
        for cat in VOICE_PROFILES:
            assert cat in CATEGORY_LABELS, f"{cat} 缺少中文标签"

    def test_labels_are_non_empty(self):
        for label in CATEGORY_LABELS.values():
            assert len(label) > 0


class TestDisplayVoiceProfiles:
    def test_runs_without_error(self, monkeypatch):
        """display_voice_profiles 应正常渲染不抛出异常。"""
        monkeypatch.setattr("voice_profiles.Console", lambda: type(
            "FakeConsole", (), {
                "print": lambda self, *a, **kw: None,
            })()
        )
        display_voice_profiles()
