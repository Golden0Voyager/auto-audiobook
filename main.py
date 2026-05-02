"""入口 — watchdog 监听 + CLI 模式 + 交互式界面。"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import CLEAN_MODE, INPUT_DIR, OUTPUT_DIR, TTS_STYLE_PRESETS
from pipeline import process_book

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

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
    print(f"\n{'='*50}")
    print("批量处理完成")
    print(f"{'='*50}")

    for i, r in enumerate(results, 1):
        status = f"成功 ({r.elapsed:.1f}s)" if r.success else f"失败: {r.error}"
        print(f"  [{i}/{len(results)}] {r.file_path.stem} - {status}")

    success = sum(1 for r in results if r.success)
    failed = len(results) - success
    total_time = sum(r.elapsed for r in results)
    print(f"\n总计: {success} 成功, {failed} 失败, 耗时 {total_time:.0f}s")
    print(f"{'='*50}")


# ── 交互式界面 ────────────────────────────────────────────────────────


def _scan_input_dir(input_dir: Path) -> list[Path]:
    """扫描 input 目录，返回支持格式的文件列表（排序）。"""
    files: list[Path] = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(input_dir.glob(f"*{ext}"))
    files.sort(key=lambda p: p.name)
    return files


def _parse_selection(text: str, max_index: int) -> list[int]:
    """解析用户选择，支持 1,3,5-8 格式。返回 0-based 索引列表。"""
    indices: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                start_idx = int(start) - 1
                end_idx = int(end) - 1
                if 0 <= start_idx <= end_idx < max_index:
                    indices.extend(range(start_idx, end_idx + 1))
            except ValueError:
                continue
        else:
            try:
                idx = int(part) - 1
                if 0 <= idx < max_index:
                    indices.append(idx)
            except ValueError:
                continue
    return sorted(set(indices))


def interactive_mode() -> None:
    """交互式终端界面。"""
    while True:
        print(f"\n{'='*40}")
        print("  Auto Audiobook - 自动化有声书生成")
        print(f"{'='*40}")
        print("  1. 交互式选择文件")
        print("  2. 监听目录 (watchdog)")
        print("  3. 退出")
        print()

        choice = input("> 请选择 [1/2/3]: ").strip()

        if choice == "1":
            files = _scan_input_dir(INPUT_DIR)
            if not files:
                print(f"\ninput/ 目录为空，请先放入 EPUB/MOBI/PDF 文件")
                continue

            print(f"\n扫描到 {len(files)} 个文件:")
            for i, f in enumerate(files, 1):
                print(f"  [{i:2d}] {f.name}")
            print(f"  [ A] 全部处理")
            print(f"  [ Q] 返回")

            selection = input("\n请选择 (可多选，如 1,3,5-8): ").strip().upper()

            if selection == "Q":
                continue
            elif selection == "A":
                selected = files
            else:
                indices = _parse_selection(selection, len(files))
                if not indices:
                    print("无效选择，请重试")
                    continue
                selected = [files[i] for i in indices]

            print(f"\n已选择 {len(selected)} 个文件:")
            for i, f in enumerate(selected, 1):
                print(f"  [{i}] {f.name}")

            confirm = input("\n确认开始处理? [Y/n]: ").strip().upper()
            if confirm == "N":
                continue

            results = asyncio.run(batch_process(selected))
            print_batch_summary(results)

        elif choice == "2":
            watch_mode()
        elif choice == "3":
            print("再见!")
            sys.exit(0)
        else:
            print("无效选择，请重试")


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
