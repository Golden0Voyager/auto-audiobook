"""入口 — watchdog 监听 + CLI 模式。"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import CLEAN_MODE, INPUT_DIR, TTS_STYLE_PRESETS
from pipeline import process_book

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".epub", ".mobi", ".pdf"}


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


async def cli_mode(file_path: Path, preview_chunks: int = 0) -> None:
    """CLI 模式：直接处理指定文件。"""
    if not file_path.exists():
        logger.error(f"文件不存在: {file_path}")
        sys.exit(1)

    await process_book(file_path, preview_chunks=preview_chunks)


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


def main() -> None:
    parser = argparse.ArgumentParser(description="自动化有声书生成引擎")
    parser.add_argument("--file", "-f", type=Path, help="直接处理指定的 EPUB/MOBI/PDF 文件")
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
        asyncio.run(cli_mode(args.file, preview_chunks=args.preview))
    else:
        watch_mode()


if __name__ == "__main__":
    main()
