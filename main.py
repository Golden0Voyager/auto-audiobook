"""入口 — watchdog 监听 + CLI 模式 + 交互式界面。"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import CLEAN_MODE, INPUT_DIR, TTS_STYLE_PRESETS
from pipeline import process_book

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 抑制 httpx/httpcore 在事件循环关闭时的清理警告
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)

SUPPORTED_EXTENSIONS = {".epub", ".mobi", ".pdf"}


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
        logger.info(f"\n{'='*50}")
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
    files: list[Path] = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(input_dir.glob(f"*{ext}"))
    files.sort(key=lambda p: p.name)
    return files


def interactive_mode() -> None:
    """交互式终端界面。"""
    console.print(Panel("[bold cyan]Auto Audiobook[/bold cyan]\n自动化有声书生成引擎", border_style="cyan"))

    while True:
        choice = questionary.select(
            "请选择操作模式:",
            choices=[
                questionary.Choice(title="交互式选择文件", value="select"),
                questionary.Choice(title="监听目录 (watchdog)", value="watch"),
                questionary.Choice(title="退出", value="exit"),
            ],
            style=questionary.Style([
                ('pointer', 'fg:#00ffff'),
                ('selected', 'fg:#00ff00'),
            ]),
        ).ask()

        if choice is None or choice == "exit":
            console.print("[dim]再见![/dim]")
            sys.exit(0)

        if choice == "watch":
            watch_mode()
            continue

        # 交互式选择文件
        files = _scan_input_dir(INPUT_DIR)
        if not files:
            console.print("[yellow]input/ 目录为空，请先放入 EPUB/MOBI/PDF 文件[/yellow]")
            continue

        choices = [
            questionary.Choice(title=f.name, value=f)
            for f in files
        ]

        selected = questionary.checkbox(
            f"扫描到 {len(files)} 个文件，用空格勾选，回车确认:",
            choices=choices,
            style=questionary.Style([
                ('checkbox', 'fg:#00ffff'),
                ('selected', 'fg:#00ff00'),
                ('pointer', 'fg:#00ffff'),
            ]),
        ).ask()

        if not selected:
            console.print("[yellow]未选择任何文件[/yellow]")
            continue

        # 确认清单
        table = Table(title="待处理文件", border_style="cyan", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=3)
        table.add_column("文件名")
        for i, f in enumerate(selected, 1):
            table.add_row(str(i), f.name)
        console.print(table)

        confirm = questionary.confirm("确认开始处理?", default=True).ask()
        if not confirm:
            continue

        results = asyncio.run(batch_process(selected))
        print_batch_summary(results)


# ── 入口 ──────────────────────────────────────────────────────────────


def main() -> None:
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
        help="TTS 朗读风格: default(默认), news(新闻), story(故事), casual(轻松), classic(经典)",
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=0,
        metavar="N",
        help="试听模式: 只合成前 N 个文本块，快速验证效果后再全量处理",
    )
    args = parser.parse_args()

    # 动态设置配置
    import config
    config.CLEAN_MODE = args.clean_mode
    config.TTS_STYLE = args.style
    config.TTS_STYLES = TTS_STYLE_PRESETS[args.style]

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
