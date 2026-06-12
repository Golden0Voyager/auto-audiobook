"""入口 — watchdog 监听 + CLI 模式 + 交互式界面。"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import shutil
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import config
from config import CLEAN_MODE, INPUT_DIR, OUTPUT_DIR, STYLE_LABELS, TTS_CACHE_DIR, TTS_STYLE_PRESETS, init_dirs
from parser import parse_file
from pipeline import process_book
from text_processor import detect_language, get_language_name
from voice_profiles import display_voice_profiles

import voice_lab

console = Console()

# ── 国际化支持 ────────────────────────────────────────────────────────
UI_LANG = "zh"  # 默认中文，可切换为 "en"

TRANSLATIONS = {
    "zh": {
        "app_title": "Auto Audiobook",
        "app_subtitle": "自动化有声书生成引擎",
        "select_mode": "请选择操作模式:",
        "mode_select": "交互式选择文件",
        "mode_watch": "监听目录 (watchdog)",
        "mode_voices": "查看所有音色",
        "mode_clean": "清理缓存",
        "mode_exit": "退出",
        "goodbye": "再见!",
        "input_empty": "input/ 目录为空，请先放入 EPUB/MOBI/PDF 文件",
        "select_all": "[全选] 选择所有文件",
        "select_files": "扫描到 {count} 个文件，用空格勾选，回车确认:",
        "no_selection": "未选择任何文件",
        "multi_lang_warning": "⚠️  本批次将共用同一语言/音色/风格设置；如需多语言混合处理，请分批选择",
        "confirm_language": "确认读本语言:",
        "sampling": "  采样 {count} 个章节，共 {chars} 字符",
        "sampling_failed": "  采样失败: {error}",
        "lang_result": "语言检测结果:",
        "lang_detected": "  检测到: {lang} (置信度: {confidence})",
        "lang_confirm": "检测到书籍语言是{lang}，确认以继续",
        "select_language": "请选择读本语言:",
        "chinese": "中文",
        "english": "英文",
        "select_style": "请选择朗读风格:",
        "pending_files": "待处理文件",
        "file_col": "文件名",
        "lang_col": "语言",
        "style_col": "朗读风格",
        "confirm_process": "确认开始处理?",
        "cache_found": "发现 {count} 个 TTS 缓存文件",
        "cache_confirm": "确认清理所有 TTS 缓存文件？",
        "cache_cleaned": "已清理 {count} 个 TTS 缓存文件",
        "cache_cancelled": "已取消清理",
        "cache_empty": "TTS 缓存为空",
        "cache_not_found": "TTS 缓存目录不存在",
        "voices_title": "可用音色配置",
    },
    "en": {
        "app_title": "Auto Audiobook",
        "app_subtitle": "Automated Audiobook Generation Engine",
        "select_mode": "Select operation mode:",
        "mode_select": "Interactive file selection",
        "mode_watch": "Watch directory (watchdog)",
        "mode_voices": "View all voice profiles",
        "mode_clean": "Clean cache",
        "mode_exit": "Exit",
        "goodbye": "Goodbye!",
        "input_empty": "input/ directory is empty, please add EPUB/MOBI/PDF files first",
        "select_all": "[Select All] Choose all files",
        "select_files": "Found {count} files, use space to select, enter to confirm:",
        "no_selection": "No files selected",
        "multi_lang_warning": "⚠️  This batch will share one language/voice/style. For mixed-language books, please process them in separate batches.",
        "confirm_language": "Confirm book language:",
        "sampling": "  Sampled {count} chapters, {chars} characters total",
        "sampling_failed": "  Sampling failed: {error}",
        "lang_result": "Language detection result:",
        "lang_detected": "  Detected: {lang} (confidence: {confidence})",
        "lang_confirm": "Detected book language is {lang}, confirm to continue",
        "select_language": "Select book language:",
        "chinese": "Chinese",
        "english": "English",
        "select_style": "Select reading style:",
        "pending_files": "Files to process",
        "file_col": "File Name",
        "lang_col": "Language",
        "style_col": "Reading Style",
        "confirm_process": "Confirm to start processing?",
        "cache_found": "Found {count} TTS cache files",
        "cache_confirm": "Confirm to clean all TTS cache files?",
        "cache_cleaned": "Cleaned {count} TTS cache files",
        "cache_cancelled": "Cleanup cancelled",
        "cache_empty": "TTS cache is empty",
        "cache_not_found": "TTS cache directory not found",
        "voices_title": "Available Voice Profiles",
    },
}


def t(key: str, **kwargs) -> str:
    """获取翻译文本。"""
    text = TRANSLATIONS[UI_LANG].get(key, key)
    return text.format(**kwargs) if kwargs else text


# FileHandler 在 import 时打开文件，必须先确保 OUTPUT_DIR 存在
# （init_dirs() 是延迟初始化，要等 main() 才执行，对 logging.basicConfig 太晚）
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 模块级保留 handler 引用，方便交互模式动态降低控制台日志级别（文件日志保留完整 INFO）
_console_log_handler = logging.StreamHandler()
_file_log_handler = logging.FileHandler(OUTPUT_DIR / "batch_run.log", encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[_console_log_handler, _file_log_handler],
)
logger = logging.getLogger(__name__)

# 抑制 httpx/httpcore 在事件循环关闭时的清理警告
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)


def _quiet_console_logging() -> None:
    """交互模式下把控制台日志降到 WARNING，避免 INFO 日志与 rich 输出交错。"""
    _console_log_handler.setLevel(logging.WARNING)


SUPPORTED_EXTENSIONS = {".epub", ".mobi", ".pdf", ".azw", ".azw3", ".kf8"}


# ── Watchdog ──────────────────────────────────────────────────────────


class BookHandler(FileSystemEventHandler):
    """监听 input/ 目录，检测到电子书自动触发处理。"""

    def __init__(self) -> None:
        self._processing: set[str] = set()

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        if str(path) in self._processing:
            return

        self._processing.add(str(path))
        logger.info(f"检测到新文件: {path.name}")
        asyncio.run(self._process(path))

    async def _process(self, path: Path) -> None:
        try:
            await process_book(path)
        except Exception as e:
            logger.error(f"处理失败: {e}")
        finally:
            self._processing.discard(str(path))


def watch_mode() -> None:
    """Watchdog 模式：监听 input/ 目录。"""
    handler = BookHandler()
    observer = Observer()
    observer.schedule(handler, str(INPUT_DIR), recursive=False)
    observer.start()

    logger.info(f"监听目录: {INPUT_DIR}")
    logger.info("将 EPUB/MOBI/PDF 文件放入该目录即可自动处理")
    logger.info("按 Ctrl+C 退出")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


# ── 批量处理 ─────────────────────────────────────────────────────────


@dataclass
class BookResult:
    file_path: Path
    success: bool
    elapsed: float
    error: str = ""


async def batch_process(files: list[Path], preview_chunks: int = 0) -> list[BookResult]:
    """串行批量处理多本书，返回每本书的结果。"""
    results: list[BookResult] = []
    total = len(files)

    for i, file_path in enumerate(files, 1):
        name = file_path.stem
        logger.info(f"{'='*50}")
        logger.info(f"[{i}/{total}] 处理中: {name}")
        logger.info(f"{'='*50}")

        start = time.time()
        try:
            await process_book(file_path, preview_chunks=preview_chunks)
            elapsed = time.time() - start
            results.append(BookResult(file_path=file_path, success=True, elapsed=elapsed))
            logger.info(f"[{i}/{total}] 完成 ({elapsed:.1f}s)")
        except Exception as e:
            elapsed = time.time() - start
            results.append(BookResult(file_path=file_path, success=False, elapsed=elapsed, error=str(e)))
            logger.error(f"[{i}/{total}] 失败: {e}")
            logger.error(traceback.format_exc())

    return results


def print_batch_summary(results: list[BookResult]) -> None:
    """输出批量处理汇总。"""
    table = Table(title="批量处理完成", border_style="cyan", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("文件名")
    table.add_column("状态", justify="right")
    table.add_column("耗时", justify="right")

    for i, r in enumerate(results, 1):
        if r.success:
            table.add_row(str(i), r.file_path.stem, "[green]成功[/green]", f"{r.elapsed:.1f}s")
        else:
            table.add_row(str(i), r.file_path.stem, f"[red]失败: {r.error}[/red]", f"{r.elapsed:.1f}s")

    console.print(table)

    success = sum(1 for r in results if r.success)
    failed = len(results) - success
    total_time = sum(r.elapsed for r in results)
    console.print(f"\n总计: [green]{success} 成功[/green], [red]{failed} 失败[/red], 耗时 {total_time:.0f}s")


# ── 交互式界面 ────────────────────────────────────────────────────────


def _scan_input_dir(input_dir: Path) -> list[Path]:
    """扫描 input 目录，返回支持格式的文件列表（排序）。"""
    files = [
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    files.sort(key=lambda p: p.name)
    return files


def _clean_cache() -> None:
    """清理 TTS 缓存。"""
    if TTS_CACHE_DIR.exists():
        cache_files = list(TTS_CACHE_DIR.glob("*.wav"))
        if cache_files:
            console.print(f"[yellow]{t('cache_found', count=len(cache_files))}[/yellow]")
            confirm = questionary.confirm(
                t("cache_confirm"),
                default=False
            ).ask()
            if confirm:
                shutil.rmtree(TTS_CACHE_DIR)
                TTS_CACHE_DIR.mkdir(exist_ok=True)
                console.print(f"[green]{t('cache_cleaned', count=len(cache_files))}[/green]")
            else:
                console.print(f"[dim]{t('cache_cancelled')}[/dim]")
        else:
            console.print(f"[yellow]{t('cache_empty')}[/yellow]")
    else:
        console.print(f"[yellow]{t('cache_not_found')}[/yellow]")


def _sample_book_text(files: list[Path]) -> str:
    """解析书籍首文件，随机采样 3 个非目录章节、每章前 600 字，用于语言检测。"""
    try:
        book = parse_file(files[0])
        chapters = [
            ch for ch in book.chapters
            if len(ch.title) > 2 and sum(len(c) for c in ch.chunks) > 200
        ] or book.chapters

        sample_count = min(3, len(chapters))
        sampled = random.sample(chapters, sample_count)
        sample_text = "\n".join(ch.chunks[0][:600] for ch in sampled if ch.chunks)

        console.print(f"[dim]{t('sampling', count=sample_count, chars=len(sample_text))}[/dim]")
        return sample_text
    except Exception as e:
        console.print(f"[yellow]{t('sampling_failed', error=e)}[/yellow]")
        return ""


def _ask_language_selection(detected_lang: str, confidence: float, style: questionary.Style) -> str:
    """显示检测结果，让用户确认或手动选择语言。"""
    lang_name = get_language_name(detected_lang)

    console.print(f"\n[bold]{t('lang_result')}[/bold]")
    console.print(f"  {t('lang_detected', lang=lang_name, confidence=f'{confidence:.0%}')}")

    if questionary.confirm(t("lang_confirm", lang=lang_name), default=True).ask():
        return detected_lang

    lang_choice = questionary.select(
        t("select_language"),
        choices=[
            questionary.Choice(title=t("chinese"), value="zh"),
            questionary.Choice(title=t("english"), value="en"),
        ],
        style=style,
    ).ask()
    return lang_choice or "zh"


def _confirm_language(files: list[Path], style: questionary.Style) -> str:
    """确认读本语言：采样文本 → 自动检测 → 用户确认/手动选择。"""
    sample_text = _sample_book_text(files)
    detected_lang, confidence = detect_language(sample_text)
    return _ask_language_selection(detected_lang, confidence, style)


def _pick_ui_language() -> str:
    """让用户选择界面语言。"""
    return questionary.select(
        "选择界面语言 / Select UI Language:",
        choices=[
            questionary.Choice(title="中文", value="zh"),
            questionary.Choice(title="English", value="en"),
        ],
        style=questionary.Style([
            ('pointer', 'fg:#00ffff bold'),
            ('selected', 'fg:#000000 bg:#00ff00 bold'),
        ]),
    ).ask() or "zh"


def _build_questionary_style() -> questionary.Style:
    """返回统一的交互式样式。"""
    return questionary.Style([
        ('pointer', 'fg:#00ffff bold'),
        ('selected', 'fg:#000000 bg:#00ff00 bold'),
        ('checkbox', 'fg:#00ffff'),
        ('highlighted', 'fg:#000000 bg:#00ff00 bold'),
    ])


def _select_files(files: list[Path], style: questionary.Style) -> list[Path] | None:
    """交互式多选文件。返回 None 表示用户未选择。"""
    choices = [questionary.Choice(title=t("select_all"), value="ALL")]
    choices += [questionary.Choice(title=f.name, value=f) for f in files]

    instruction = "空格选择，a全选，回车确认" if UI_LANG == "zh" else "space to select, a to toggle all, enter to confirm"
    selected = questionary.checkbox(
        t("select_files", count=len(files)),
        choices=choices,
        style=style,
        instruction=instruction,
    ).ask()

    if not selected:
        return None
    if "ALL" in selected:
        return files
    return [f for f in selected if f != "ALL"]


def _show_pending_summary(files: list[Path], language: str, style_choice: str, voice: str) -> None:
    """显示待处理文件清单和配置摘要。"""
    table = Table(
        title=t("pending_files"),
        border_style="cyan",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("#", style="dim", width=3)
    table.add_column(t("file_col"))
    for i, f in enumerate(files, 1):
        table.add_row(str(i), f.name)
    console.print(table)
    console.print(
        f"[cyan]{t('lang_col')}: {get_language_name(language)} | "
        f"音色: {voice} | "
        f"{t('style_col')}: {STYLE_LABELS[UI_LANG][style_choice]}[/cyan]"
    )


def _apply_processing_config(language: str, style_choice: str, voice: str) -> None:
    """把用户选择的语言、音色和风格写入运行时配置。"""
    config.TTS_VOICES[language] = voice
    config.TTS_STYLE = style_choice
    config.TTS_STYLES = TTS_STYLE_PRESETS[style_choice]


def interactive_mode() -> None:
    """交互式终端界面。"""
    global UI_LANG
    # 进入交互模式后，控制台只显示 WARNING+ 日志，避免与 rich 输出交错
    _quiet_console_logging()
    UI_LANG = _pick_ui_language()
    style = _build_questionary_style()

    console.print(
        Panel(f"[bold cyan]{t('app_title')}[/bold cyan]\n{t('app_subtitle')}", border_style="cyan")
    )

    while True:
        choice = questionary.select(
            t("select_mode"),
            choices=[
                questionary.Choice(title=t("mode_select"), value="select"),
                questionary.Choice(title=t("mode_watch"), value="watch"),
                questionary.Choice(title=t("mode_voices"), value="voices"),
                questionary.Choice(title=t("mode_clean"), value="clean"),
                questionary.Choice(title=t("mode_exit"), value="exit"),
            ],
            style=style,
        ).ask()

        if choice is None or choice == "exit":
            console.print(f"[dim]{t('goodbye')}[/dim]")
            sys.exit(0)

        if choice == "watch":
            watch_mode()
            continue

        if choice == "voices":
            display_voice_profiles()
            continue

        if choice == "clean":
            _clean_cache()
            continue

        # ── 文件选择 -> 语言确认 -> 风格选择 -> 处理 ──
        files = _scan_input_dir(INPUT_DIR)
        if not files:
            console.print(f"[yellow]{t('input_empty')}[/yellow]")
            continue

        selected = _select_files(files, style)
        if selected is None:
            console.print(f"[yellow]{t('no_selection')}[/yellow]")
            continue

        # 多文件批处理时提醒：当前批次会共享单一语言/音色/风格
        if len(selected) > 1:
            console.print(f"[yellow]{t('multi_lang_warning')}[/yellow]")

        console.print(f"\n[bold]{t('confirm_language')}[/bold]")
        language = _confirm_language(selected, style)

        # 提前抽一次试听文本：用户重选音色/风格时复用同一段文本，
        # 既保证 A/B 对比公平，也让相同 (voice, style) 直接命中 TTS 缓存。
        preview_text = voice_lab.prepare_preview_text(selected[0], language)

        # 试听→确认循环：n 不满意则重进试听对比室，保留书籍/语言/试听文本
        while True:
            console.print("\n[bold]进入试听对比室…[/bold]")
            voice, style_choice = asyncio.run(
                voice_lab.run_voice_lab(selected[0], language, preview_text=preview_text)
            )
            _apply_processing_config(language, style_choice, voice)

            _show_pending_summary(selected, language, style_choice, voice)

            if questionary.confirm(t("confirm_process"), default=True).ask():
                break

        results = asyncio.run(batch_process(selected))
        print_batch_summary(results)


# ── 入口 ──────────────────────────────────────────────────────────────


def main() -> None:
    init_dirs()

    parser = argparse.ArgumentParser(description="自动化有声书生成引擎")
    parser.add_argument(
        "--file", "-f",
        type=Path,
        nargs="+",
        help="直接处理指定的一个或多个 EPUB/MOBI/PDF 文件",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="批量处理指定目录下的所有支持格式文件",
    )
    parser.add_argument(
        "--clean-mode",
        choices=["rule", "llm"],
        default=CLEAN_MODE,
        help="文本清洗模式: rule (规则引擎, 默认) 或 llm (大模型)",
    )
    parser.add_argument(
        "--style",
        choices=list(TTS_STYLE_PRESETS.keys()),
        default="default",
        help="TTS 朗读风格: default(默认), news(新闻), story(故事), biography(传记), nonfiction(知识)",
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=0,
        metavar="N",
        help="试听模式: 只合成前 N 个文本块，快速验证效果后再全量处理",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="列出所有可用的音色配置",
    )
    args = parser.parse_args()

    # 动态设置配置
    config.CLEAN_MODE = args.clean_mode
    config.TTS_STYLE = args.style
    config.TTS_STYLES = TTS_STYLE_PRESETS[args.style]

    # 列出音色
    if args.list_voices:
        display_voice_profiles()
        return

    if args.file:
        # CLI 模式：处理指定文件（支持多文件）
        for f in args.file:
            if not f.exists():
                logger.error(f"文件不存在: {f}")
                sys.exit(1)
        if len(args.file) == 1:
            asyncio.run(process_book(args.file[0], preview_chunks=args.preview))
        else:
            results = asyncio.run(batch_process(args.file, preview_chunks=args.preview))
            print_batch_summary(results)
    elif args.input_dir:
        # 批量模式：处理目录下所有文件
        if not args.input_dir.exists():
            logger.error(f"目录不存在: {args.input_dir}")
            sys.exit(1)
        files = _scan_input_dir(args.input_dir)
        if not files:
            logger.error(f"目录中没有支持的文件: {args.input_dir}")
            sys.exit(1)
        logger.info(f"扫描到 {len(files)} 个文件")
        results = asyncio.run(batch_process(files, preview_chunks=args.preview))
        print_batch_summary(results)
    else:
        # 交互式界面
        interactive_mode()


if __name__ == "__main__":
    main()
