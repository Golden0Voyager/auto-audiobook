"""main.interactive_mode 交互循环测试 — mock questionary 验证模式路由和文件处理流程。"""

from __future__ import annotations

from pathlib import Path

from models import BookData, Chapter


# ── mock 辅助 ──────────────────────────────────────────────


class FakeAsk:
    """模拟 questionary 的 .ask() 方法。"""
    def __init__(self, return_value):
        self.return_value = return_value

    def ask(self):
        return self.return_value


def _make_chapter(title: str, chars: int = 250) -> Chapter:
    """生成指定长度的中文章节。"""
    text = "测试文本。" * (chars // 5 + 1)
    return Chapter(title=title, chunks=[text[:chars]])


def _setup_basic_mocks(monkeypatch):
    """所有测试共享的基础 mock。"""
    monkeypatch.setattr("main.console.print", lambda *a, **kw: None)
    monkeypatch.setattr("main._quiet_console_logging", lambda: None)


def _make_select_iter(values):
    """返回 questionary.select 替代函数，每次调用从序列取下一个值。"""
    it = iter(values)
    return lambda *a, **kw: FakeAsk(next(it))


def _make_sys_exit():
    def fake_exit(code=0):
        raise SystemExit(code)
    return fake_exit


def _setup_process_mocks(monkeypatch, epub):
    """完整流程测试的 mock 环境配置。返回 call_count 字典供断言。"""
    calls = {
        "batch_process": 0,
        "voice_lab": 0,
        "apply_config": 0,
    }

    monkeypatch.setattr("main._scan_input_dir", lambda p: [epub])
    monkeypatch.setattr(
        "main.parse_file",
        lambda p: BookData(
            title="测试书", author="作者", language="zh",
            chapters=[_make_chapter("第一章", 250), _make_chapter("第二章", 250)],
        ),
    )
    monkeypatch.setattr(
        "main.voice_lab.prepare_preview_text",
        lambda *a, **kw: "预览文本。",
    )

    async def fake_run_voice_lab(*a, **kw):
        calls["voice_lab"] += 1
        return ("voice_01", "news")

    monkeypatch.setattr("main.voice_lab.run_voice_lab", fake_run_voice_lab)

    def fake_apply_config(*a, **kw):
        calls["apply_config"] += 1

    monkeypatch.setattr("main._apply_processing_config", fake_apply_config)

    async def fake_batch_process(files, **kw):
        from main import BookResult
        calls["batch_process"] += 1
        return [BookResult(file_path=f, success=True, elapsed=1.0) for f in files]

    monkeypatch.setattr("main.batch_process", fake_batch_process)
    monkeypatch.setattr("main.print_batch_summary", lambda x: None)
    monkeypatch.setattr("main.sys.exit", _make_sys_exit())

    return calls


# ── 模式路由 ─────────────────────────────────────────────


class TestInteractiveModeRouting:
    """测试 interactive_mode 的主菜单路由。每个测试执行一种模式后退出。"""

    def test_mode_exit(self, monkeypatch):
        """选择「退出」→ sys.exit(0)。"""
        _setup_basic_mocks(monkeypatch)
        monkeypatch.setattr("main.questionary.select", _make_select_iter(["zh", "exit"]))
        monkeypatch.setattr("main.sys.exit", _make_sys_exit())

        try:
            from main import interactive_mode
            interactive_mode()
        except SystemExit:
            pass

    def test_mode_watch(self, monkeypatch):
        """选择「监听目录」→ watch_mode() 不阻塞 → 返回菜单 → 退出。"""
        _setup_basic_mocks(monkeypatch)
        watch_called = {"n": 0}

        def fake_watch():
            watch_called["n"] += 1

        monkeypatch.setattr("main.watch_mode", fake_watch)
        monkeypatch.setattr("main.questionary.select", _make_select_iter(["zh", "watch", "exit"]))
        monkeypatch.setattr("main.sys.exit", _make_sys_exit())

        try:
            from main import interactive_mode
            interactive_mode()
        except SystemExit:
            pass
        assert watch_called["n"] == 1

    def test_mode_voices(self, monkeypatch):
        """选择「查看音色」→ display_voice_profiles() → 返回菜单 → 退出。"""
        _setup_basic_mocks(monkeypatch)
        voices_called = {"n": 0}

        def fake_voices():
            voices_called["n"] += 1

        monkeypatch.setattr("main.display_voice_profiles", fake_voices)
        monkeypatch.setattr("main.questionary.select", _make_select_iter(["zh", "voices", "exit"]))
        monkeypatch.setattr("main.sys.exit", _make_sys_exit())

        try:
            from main import interactive_mode
            interactive_mode()
        except SystemExit:
            pass
        assert voices_called["n"] == 1

    def test_mode_clean_cache(self, monkeypatch):
        """选择「清理缓存」→ _clean_cache() → 返回菜单 → 退出。"""
        _setup_basic_mocks(monkeypatch)
        clean_called = {"n": 0}

        def fake_clean():
            clean_called["n"] += 1

        monkeypatch.setattr("main._clean_cache", fake_clean)
        monkeypatch.setattr("main.questionary.select", _make_select_iter(["zh", "clean", "exit"]))
        monkeypatch.setattr("main.sys.exit", _make_sys_exit())

        try:
            from main import interactive_mode
            interactive_mode()
        except SystemExit:
            pass
        assert clean_called["n"] == 1


# ── 输入目录与文件选择 ───────────────────────────────────


class TestInteractiveModeFileSelection:
    """测试文件选择阶段的空目录和取消选择。"""

    def _run_and_capture_print(self, monkeypatch, select_values, **extra_mocks):
        """运行 interactive_mode 并捕获 console.print 消息。"""
        _setup_basic_mocks(monkeypatch)

        # 允许子类覆盖 console.print
        printed = []

        def fake_print(*a, **kw):
            printed.append(str(a[0]))

        monkeypatch.setattr("main.console.print", fake_print)
        monkeypatch.setattr("main.questionary.select", _make_select_iter(select_values))
        monkeypatch.setattr("main.sys.exit", _make_sys_exit())

        for target, val in extra_mocks.items():
            monkeypatch.setattr(target, val)

        try:
            from main import interactive_mode
            interactive_mode()
        except SystemExit:
            pass
        return printed

    def test_input_empty_shows_warning(self, monkeypatch):
        """input/ 无文件 → 打印警告 → 返回菜单 → 退出。"""
        printed = self._run_and_capture_print(
            monkeypatch,
            ["zh", "select", "exit"],
            **{"main._scan_input_dir": lambda p: []},
        )
        assert any("空" in msg or "empty" in msg.lower() for msg in printed)

    def test_no_selection_shows_warning(self, monkeypatch):
        """文件选择未勾选 → 打印警告 → 返回菜单 → 退出。"""
        printed = self._run_and_capture_print(
            monkeypatch,
            ["zh", "select", "exit"],
            **{
                "main._scan_input_dir": lambda p: [Path("test.epub")],
                "main.questionary.checkbox": lambda *a, **kw: FakeAsk(None),
            },
        )
        assert any("未选择" in msg or "no selection" in msg.lower() for msg in printed)


# ── 完整处理流程 ────────────────────────────────────────


class TestInteractiveModeFullFlow:
    """完整的文件选择→确认→试听→处理→退出流程。"""

    def test_process_files_then_exit(self, monkeypatch):
        """select files → confirm lang → voice lab → process → exit."""
        _setup_basic_mocks(monkeypatch)
        epub = Path("test_book.epub")

        # questionary mock 序列
        monkeypatch.setattr(
            "main.questionary.select",
            _make_select_iter(["zh", "select", "exit"]),
        )
        monkeypatch.setattr(
            "main.questionary.confirm",
            _make_select_iter([True, True]),  # _confirm_language, voice loop confirm
        )
        monkeypatch.setattr(
            "main.questionary.checkbox",
            lambda *a, **kw: FakeAsk([epub]),
        )

        calls = _setup_process_mocks(monkeypatch, epub)

        from main import interactive_mode
        try:
            interactive_mode()
        except SystemExit:
            pass

        assert calls["voice_lab"] == 1
        assert calls["batch_process"] == 1
        assert calls["apply_config"] == 1

    def test_process_with_language_correction(self, monkeypatch):
        """用户对自动检测的语言说「不」，手动选择中文。"""
        _setup_basic_mocks(monkeypatch)
        epub = Path("test_book.epub")

        # questionary mock 序列:
        # pick_ui → zh
        # mode select → select
        # _confirm_language: confirm → False (拒绝自动检测)
        #   → then questionary.select for manual lang → "zh"
        # voice lab loop: confirm → True (确认处理)
        # mode select → exit
        monkeypatch.setattr(
            "main.questionary.select",
            _make_select_iter(["zh", "select", "zh", "exit"]),
        )
        monkeypatch.setattr(
            "main.questionary.confirm",
            _make_select_iter([False, True]),
        )
        monkeypatch.setattr(
            "main.questionary.checkbox",
            lambda *a, **kw: FakeAsk([epub]),
        )

        calls = _setup_process_mocks(monkeypatch, epub)

        from main import interactive_mode
        try:
            interactive_mode()
        except SystemExit:
            pass

        assert calls["voice_lab"] == 1
        assert calls["batch_process"] == 1
        assert calls["apply_config"] == 1
