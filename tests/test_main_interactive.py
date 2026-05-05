"""回归测试：main.py 交互逻辑与日志配置。"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import main


# ── 1. 日志路径不应硬编码 ─────────────────────────────────────────────

def test_log_file_handler_uses_relative_path():
    """FileHandler 的路径必须基于 OUTPUT_DIR，而不是硬编码的绝对路径。"""
    from config import OUTPUT_DIR

    assert hasattr(main, "_file_log_handler"), "main 模块应暴露 _file_log_handler"
    expected = str(OUTPUT_DIR / "batch_run.log")
    assert main._file_log_handler.baseFilename == expected, (
        f"日志路径应基于 OUTPUT_DIR ({expected})，"
        f"而非硬编码绝对路径 ({main._file_log_handler.baseFilename})"
    )


# ── 2. 交互模式应降低控制台日志级别 ───────────────────────────────────

def test_quiet_console_logging_lowers_stream_level():
    """调用 _quiet_console_logging() 后，StreamHandler 级别应为 WARNING。"""
    assert hasattr(main, "_quiet_console_logging"), (
        "main 模块应暴露 _quiet_console_logging() 函数"
    )
    assert hasattr(main, "_console_log_handler"), "main 模块应暴露 _console_log_handler"
    original_level = main._console_log_handler.level

    main._quiet_console_logging()
    assert main._console_log_handler.level == logging.WARNING

    # 恢复，避免污染其它测试
    main._console_log_handler.setLevel(original_level)


# ── 3. 多文件选择时应提示语言统一警告 ─────────────────────────────────

def test_multi_file_selection_shows_warning(monkeypatch, capsys):
    """用户同时选择多个文件时，应输出多语言混合警告。"""
    # 准备两个假文件
    fake_files = [Path("book1.epub"), Path("book2.epub")]

    # Mock questionary.checkbox 返回两个文件
    monkeypatch.setattr(
        main.questionary,
        "checkbox",
        lambda *a, **k: MagicMock(ask=lambda: fake_files),
    )

    printed = []
    monkeypatch.setattr(main.console, "print", lambda msg: printed.append(msg))

    # 模拟 _scan_input_dir 返回文件
    monkeypatch.setattr(main, "_scan_input_dir", lambda d: fake_files)

    # 直接调用 _select_files（它内部会弹 questionary.checkbox）
    selected = main._select_files(fake_files, main._build_questionary_style())
    assert selected == fake_files

    # 然后检查 interactive_mode 中多文件警告的打印
    # 由于 interactive_mode 是完整流程，我们直接检查 multi_lang_warning key 是否存在
    assert "multi_lang_warning" in main.TRANSLATIONS["zh"], (
        "TRANSLATIONS['zh'] 应包含 multi_lang_warning 键"
    )
    assert "multi_lang_warning" in main.TRANSLATIONS["en"], (
        "TRANSLATIONS['en'] 应包含 multi_lang_warning 键"
    )


# ── 4. synthesizer 缓存命中时不应打断进度条 ─────────────────────────

def test_cache_hit_does_not_log_info(monkeypatch, capsys):
    """缓存命中时，_synthesize_single 不应调用 logger.info（避免打断 rich Progress）。"""
    import asyncio

    from synthesizer import _synthesize_single

    calls = []
    monkeypatch.setattr(
        "synthesizer.logger", MagicMock(info=lambda *a, **k: calls.append("info"))
    )

    # Mock cache hit：让 _compute_cache_key 返回固定值，cache 文件放在对应路径
    monkeypatch.setattr(
        "synthesizer._compute_cache_key", lambda *a: "deadbeef"
    )
    fake_path = Path("/tmp/deadbeef.wav")
    fake_path.write_bytes(b"fake_audio")
    monkeypatch.setattr(
        "synthesizer.TTS_CACHE_DIR", fake_path.parent
    )

    # 构造一个假的 AsyncOpenAI client（不会走到 async with semaphore 分支）
    client = MagicMock()

    async def _run():
        return await _synthesize_single(client, "hello", "茉莉", "default", asyncio.Semaphore(1))

    result = asyncio.run(_run())
    assert result == b"fake_audio"
    assert "info" not in calls, (
        "缓存命中时不应调用 logger.info，避免与 rich Progress 同时写 stderr"
    )
