"""回归测试：main.py 交互逻辑与日志配置。"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

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

    try:
        main._quiet_console_logging()
        assert main._console_log_handler.level == logging.WARNING
    finally:
        # 即使 assert 失败也要恢复，避免污染后续测试
        main._console_log_handler.setLevel(original_level)


# ── 3. 多文件警告翻译键应存在 ─────────────────────────────────────────

def test_multi_lang_warning_translations_exist():
    """multi_lang_warning 翻译键在 zh / en 两种语言下都应存在且非空。

    interactive_mode 中 ``if len(selected) > 1`` 分支依赖此键；
    缺失会导致 t() 静默回退为 key 字面量，破坏用户体验。
    """
    for lang in ("zh", "en"):
        assert "multi_lang_warning" in main.TRANSLATIONS[lang], (
            f"TRANSLATIONS['{lang}'] 应包含 multi_lang_warning 键"
        )
        assert main.TRANSLATIONS[lang]["multi_lang_warning"], (
            f"TRANSLATIONS['{lang}']['multi_lang_warning'] 不应为空"
        )


# ── 4. synthesizer 缓存命中时不应打断进度条 ─────────────────────────

def test_cache_hit_does_not_log_info(monkeypatch, tmp_path):
    """缓存命中时，_synthesize_single 不应调用 logger.info（避免打断 rich Progress）。"""
    import asyncio

    from synthesizer import _synthesize_single

    calls = []
    monkeypatch.setattr(
        "synthesizer.logger", MagicMock(info=lambda *a, **k: calls.append("info"))
    )

    # 用 tmp_path 隔离缓存目录，pytest 自动清理；避免污染 /tmp
    monkeypatch.setattr("synthesizer._compute_cache_key", lambda *a: "deadbeef")
    monkeypatch.setattr("synthesizer.TTS_CACHE_DIR", tmp_path)
    (tmp_path / "deadbeef.wav").write_bytes(b"fake_audio")

    # 构造一个假的 AsyncOpenAI client（不会走到 async with semaphore 分支）
    client = MagicMock()

    async def _run():
        return await _synthesize_single(client, "hello", "茉莉", "default", asyncio.Semaphore(1))

    result = asyncio.run(_run())
    assert result == b"fake_audio"
    assert "info" not in calls, (
        "缓存命中时不应调用 logger.info，避免与 rich Progress 同时写 stderr"
    )
