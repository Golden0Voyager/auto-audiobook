"""main 单元测试 — 翻译、文件扫描、日志、批量处理、CLI 参数、交互逻辑 mock。"""

from __future__ import annotations

import logging

from config import OUTPUT_DIR, TTS_STYLE_PRESETS

# ── 1. 翻译函数 ──────────────────────────────────────────────────────


class TestTranslation:
    def test_returns_translated_text(self):
        from main import t
        assert t("app_title") == "Auto Audiobook"

    def test_fallback_to_key_when_missing(self):
        from main import t
        assert t("nonexistent_key_xyz") == "nonexistent_key_xyz"

    def test_format_string_interpolation(self):
        from main import t
        result = t("select_files", count=5)
        assert "5" in result

    def test_english_translation_exists(self):
        from main import TRANSLATIONS
        # 验证中英文都有关键翻译
        for lang in ("zh", "en"):
            assert "app_title" in TRANSLATIONS[lang]
            assert "goodbye" in TRANSLATIONS[lang]
            assert "confirm_process" in TRANSLATIONS[lang]
            assert "mode_select" in TRANSLATIONS[lang]
            assert "select_files" in TRANSLATIONS[lang]


# ── 2. 日志配置 ──────────────────────────────────────────────────────


class TestLogging:
    def test_quiet_console_logging_sets_warning(self):
        from main import _console_log_handler, _quiet_console_logging
        original = _console_log_handler.level
        try:
            _quiet_console_logging()
            assert _console_log_handler.level == logging.WARNING
        finally:
            _console_log_handler.setLevel(original)

    def test_file_handler_path_based_on_output_dir(self):
        from main import _file_log_handler
        expected = str(OUTPUT_DIR / "batch_run.log")
        assert _file_log_handler.baseFilename == expected


# ── 3. 文件扫描 ──────────────────────────────────────────────────────


class TestScanInputDir:
    def test_returns_supported_files_sorted(self, tmp_path):
        from main import _scan_input_dir
        (tmp_path / "b.epub").write_text("")
        (tmp_path / "a.epub").write_text("")
        (tmp_path / "c.pdf").write_text("")
        files = _scan_input_dir(tmp_path)
        names = [p.name for p in files]
        assert names == ["a.epub", "b.epub", "c.pdf"]

    def test_case_insensitive_extensions(self, tmp_path):
        from main import _scan_input_dir
        (tmp_path / "book.EPUB").write_text("")
        (tmp_path / "doc.PDF").write_text("")
        files = _scan_input_dir(tmp_path)
        assert len(files) == 2

    def test_ignores_unsupported_formats(self, tmp_path):
        from main import _scan_input_dir
        (tmp_path / "book.epub").write_text("")
        (tmp_path / "readme.txt").write_text("")
        (tmp_path / "image.png").write_text("")
        files = _scan_input_dir(tmp_path)
        assert len(files) == 1
        assert files[0].suffix == ".epub"

    def test_empty_dir_returns_empty_list(self, tmp_path):
        from main import _scan_input_dir
        assert _scan_input_dir(tmp_path) == []


# ── 4. 辅助函数 ──────────────────────────────────────────────────────


class TestAuxFunctions:
    def test_build_questionary_style(self):
        from main import _build_questionary_style
        style = _build_questionary_style()
        assert style is not None

    def test_apply_processing_config(self):
        import config as _cfg
        from main import _apply_processing_config
        # 保存原始值
        orig_voices = dict(_cfg.TTS_VOICES)
        orig_style = _cfg.TTS_STYLE
        orig_styles = dict(_cfg.TTS_STYLES)
        try:
            _apply_processing_config("zh", "news", "白桦")
            assert _cfg.TTS_VOICES["zh"] == "白桦"
            assert _cfg.TTS_STYLE == "news"
            assert TTS_STYLE_PRESETS["news"] == _cfg.TTS_STYLES
        finally:
            _cfg.TTS_VOICES.update(orig_voices)
            _cfg.TTS_STYLE = orig_style
            _cfg.TTS_STYLES = orig_styles


# ── 5. 批量处理 ──────────────────────────────────────────────────────


class TestBatchProcess:
    async def test_single_file_success(self, monkeypatch, tmp_path):
        from main import batch_process

        async def fake_process_book(path, **kw):
            return tmp_path / "output"

        monkeypatch.setattr("main.process_book", fake_process_book)

        results = await batch_process([tmp_path / "test.epub"])
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].error == ""

    async def test_single_file_failure(self, monkeypatch, tmp_path):
        from main import batch_process

        async def fake_fail(path, **kw):
            raise RuntimeError("Processing error")

        monkeypatch.setattr("main.process_book", fake_fail)

        results = await batch_process([tmp_path / "bad.epub"])
        assert len(results) == 1
        assert results[0].success is False
        assert "Processing error" in results[0].error

    async def test_multiple_files_mixed_results(self, monkeypatch, tmp_path):
        from main import batch_process

        call_count = {"n": 0}

        async def fake_mixed(path, **kw):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise ValueError("Second book failed")
            return tmp_path / "output"

        monkeypatch.setattr("main.process_book", fake_mixed)

        files = [tmp_path / "a.epub", tmp_path / "b.epub", tmp_path / "c.epub"]
        results = await batch_process(files)
        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    def test_print_batch_summary(self, monkeypatch, tmp_path):
        """print_batch_summary 应正常渲染不抛出异常。"""
        from main import BookResult, print_batch_summary

        console_mock_calls = []
        monkeypatch.setattr("main.console.print", lambda *a, **k: console_mock_calls.append(a[0]))

        results = [
            BookResult(file_path=tmp_path / "ok.epub", success=True, elapsed=10.5),
            BookResult(file_path=tmp_path / "fail.epub", success=False, elapsed=5.2, error="timeout"),
        ]
        print_batch_summary(results)
        assert len(console_mock_calls) >= 1


# ── 6. CLI 参数解析 ────────────────────────────────────────────────


class TestMainEntryPoint:
    def test_list_voices(self, monkeypatch):
        """--list-voices 应调用 display_voice_profiles 后退出。"""
        import sys
        monkeypatch.setattr(sys, "argv", ["main.py", "--list-voices"])

        called = {"display_voices": False}

        def fake_display():
            called["display_voices"] = True

        monkeypatch.setattr("main.display_voice_profiles", fake_display)

        from main import main
        main()
        assert called["display_voices"] is True

    def test_file_not_found_exits(self, monkeypatch):
        """--file 指定不存在的文件应打印错误并退出。"""
        import sys
        monkeypatch.setattr(sys, "argv", ["main.py", "--file", "/nonexistent/book.epub"])

        exit_code = [None]

        def fake_exit(code):
            exit_code[0] = code
            raise SystemExit(code)

        monkeypatch.setattr("main.sys.exit", fake_exit)

        import contextlib

        from main import main
        with contextlib.suppress(SystemExit):
            main()
        assert exit_code[0] == 1

    def test_file_single_process(self, monkeypatch):
        """--file 指定单个文件应调用 process_book。"""
        import sys
        monkeypatch.setattr(sys, "argv", ["main.py", "--file", "/tmp/test_book.epub"])

        call_count = {"n": 0}

        async def fake_process(path, **kw):
            call_count["n"] += 1

        monkeypatch.setattr("main.process_book", fake_process)
        monkeypatch.setattr("main.Path.exists", lambda self: True)

        from main import main
        main()
        assert call_count["n"] == 1

    def test_style_flag(self, monkeypatch):
        """--style 参数应更新运行时配置。"""
        import sys
        monkeypatch.setattr(sys, "argv", ["main.py", "--style", "news", "--list-voices"])

        def fake_display():
            pass

        monkeypatch.setattr("main.display_voice_profiles", fake_display)

        import config
        from main import main
        orig_style = config.TTS_STYLE
        try:
            main()
            assert config.TTS_STYLE == "news"
        finally:
            config.TTS_STYLE = orig_style


# ── 7. 清理缓存 (mock) ──────────────────────────────────────────────


class TestCleanCache:
    def test_cache_cleaned_when_confirmed(self, monkeypatch, tmp_path):
        """用户确认后清理 TTS 缓存。"""
        from main import _clean_cache

        monkeypatch.setattr("main.TTS_CACHE_DIR", tmp_path)
        (tmp_path / "abc.wav").write_text("")
        (tmp_path / "def.wav").write_text("")

        class FakeConfirm:
            def ask(self):
                return True

        monkeypatch.setattr("main.questionary.confirm", lambda msg, **kw: FakeConfirm())
        monkeypatch.setattr("main.console.print", lambda *a, **k: None)

        _clean_cache()
        # 缓存目录应被重新创建（清空）
        assert tmp_path.exists()

    def test_cache_cancelled(self, monkeypatch, tmp_path):
        """用户取消后缓存文件应保留。"""
        from main import _clean_cache

        monkeypatch.setattr("main.TTS_CACHE_DIR", tmp_path)
        (tmp_path / "keep.wav").write_text("keep")

        class FakeConfirm:
            def ask(self):
                return False

        monkeypatch.setattr("main.questionary.confirm", lambda msg, **kw: FakeConfirm())
        monkeypatch.setattr("main.console.print", lambda *a, **k: None)

        _clean_cache()
        assert (tmp_path / "keep.wav").exists()
