"""pipeline 单元测试 — 工具函数、清洗缓存、章节管理、process_book mock。"""

from __future__ import annotations

from pathlib import Path

from models import CleanedChapter
from pipeline import (
    _build_output_dirname,
    _get_cache_path,
    _get_existing_chapters,
    _load_cleaned_cache,
    _sanitize_dirname,
    _save_cleaned_cache,
    _truncate_to_chunks,
)


class TestGetCachePath:
    def test_returns_path_in_cache_dir(self, monkeypatch, tmp_path):
        import config
        monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
        path = _get_cache_path(tmp_path / "test.epub")
        assert str(path).startswith(str(tmp_path / ".cache"))
        assert path.suffix == ".json"
        assert "test" in path.stem

    def test_creates_cache_dir(self, monkeypatch, tmp_path):
        import config
        monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
        cache_dir = tmp_path / ".cache"
        assert not cache_dir.exists()
        _get_cache_path(tmp_path / "book.epub")
        assert cache_dir.exists()


class TestSaveAndLoadCleanedCache:
    def test_save_and_load_roundtrip(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        cleaned = [
            CleanedChapter(title="第1章", chunks=["a", "b"]),
            CleanedChapter(title="第2章", chunks=["c"]),
        ]
        _save_cleaned_cache(cache_path, cleaned, "测试书", "作者", "zh")
        assert cache_path.exists()

        loaded = _load_cleaned_cache(cache_path)
        assert loaded is not None
        title, author, language, chapters = loaded
        assert title == "测试书"
        assert author == "作者"
        assert language == "zh"
        assert len(chapters) == 2
        assert chapters[0].title == "第1章"
        assert chapters[0].chunks == ["a", "b"]
        assert chapters[1].chunks == ["c"]

    def test_load_non_existent_returns_none(self):
        assert _load_cleaned_cache(Path("/nonexistent/cache.json")) is None

    def test_load_corrupt_json_returns_none(self, tmp_path):
        cache_path = tmp_path / "corrupt.json"
        cache_path.write_text("{invalid json}", encoding="utf-8")
        assert _load_cleaned_cache(cache_path) is None


class TestTruncateToChunks:
    def test_no_truncation_needed(self):
        chapters = [CleanedChapter(title="章1", chunks=["a", "b", "c"])]
        result = _truncate_to_chunks(chapters, 10)
        assert len(result) == 1
        assert len(result[0].chunks) == 3

    def test_truncates_across_chapters(self):
        chapters = [
            CleanedChapter(title="章1", chunks=["a", "b", "c"]),
            CleanedChapter(title="章2", chunks=["d", "e"]),
        ]
        result = _truncate_to_chunks(chapters, 3)
        assert len(result) == 1  # 只保留第一个完整章节
        assert result[0].chunks == ["a", "b", "c"]

    def test_truncates_mid_chapter(self):
        chapters = [
            CleanedChapter(title="章1", chunks=["a", "b", "c"]),
            CleanedChapter(title="章2", chunks=["d", "e"]),
        ]
        result = _truncate_to_chunks(chapters, 4)
        assert len(result) == 2
        assert result[0].chunks == ["a", "b", "c"]
        assert result[1].chunks == ["d"]  # 只取 1 个

    def test_zero_max_returns_empty(self):
        chapters = [CleanedChapter(title="章1", chunks=["a", "b"])]
        result = _truncate_to_chunks(chapters, 0)
        assert result == []


class TestBuildOutputDirname:
    def test_with_date_and_issue(self):
        """从文件名提取日期和期号。"""
        fp = Path("2026年04月27日 (第16期).epub")
        result = _build_output_dirname(fp, "默认书名")
        assert "2026年04月27日" in result
        assert "第16期" in result

    def test_fallback_to_title(self):
        """没有日期模式时回退到书名。"""
        fp = Path("一本普通的书.epub")
        result = _build_output_dirname(fp, "我的书")
        assert result == "我的书"

    def test_sanitizes_fallback_title(self):
        """书名中包含非法字符时会被清理。"""
        fp = Path("test.epub")
        result = _build_output_dirname(fp, "我的:书/啊")
        assert ":" not in result
        assert "/" not in result


class TestSanitizeDirname:
    def test_removes_illegal_chars(self):
        assert _sanitize_dirname("a:b") == "a_b"
        assert _sanitize_dirname('a"b') == "a_b"
        assert _sanitize_dirname("a/b") == "a_b"
        assert _sanitize_dirname("a\\b") == "a_b"
        assert _sanitize_dirname("a?b") == "a_b"
        assert _sanitize_dirname("a*b") == "a_b"

    def test_strips_whitespace(self):
        assert _sanitize_dirname(" 书名 ") == "书名"

    def test_clean_name_unchanged(self):
        assert _sanitize_dirname("一本正常的书名") == "一本正常的书名"


class TestGetExistingChapters:
    def test_nonexistent_dir_returns_empty(self):
        assert _get_existing_chapters(Path("/nonexistent")) == set()

    def test_empty_dir_returns_empty(self, tmp_path):
        assert _get_existing_chapters(tmp_path) == set()

    def test_finds_valid_mp3(self, tmp_path, monkeypatch):
        """文件名匹配 "01_标题.mp3" 且内容有效时才收录。"""
        mp3_file = tmp_path / "01_第一章.mp3"
        mp3_file.write_text("fake mp3")

        # Mock mutagen.MP3 to return valid audio info
        class FakeMP3Info:
            length = 100.0

        class FakeMP3:
            info = FakeMP3Info()

            def __init__(self, _path):
                pass

        monkeypatch.setattr("pipeline.MP3", FakeMP3)

        result = _get_existing_chapters(tmp_path)
        assert 1 in result

    def test_skips_non_matching_filenames(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "chapter_one.mp3").write_text("x")
        result = _get_existing_chapters(tmp_path)
        assert result == set()

    def test_skips_corrupt_mp3(self, tmp_path):
        (tmp_path / "02_第二章.mp3").write_text("not an mp3")
        result = _get_existing_chapters(tmp_path)
        assert result == set()
