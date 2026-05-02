"""主流水线 — 串接 parser → cleaner → synthesizer → assembler。"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from assembler import assemble_book
from cleaner import CleanedChapter, clean_chapters
from config import CLEAN_MODE, OUTPUT_DIR
from parser import parse_file
from rule_cleaner import clean_chapters as rule_clean_chapters
from synthesizer import ChapterAudio, synthesize_chapters

logger = logging.getLogger(__name__)


def _get_cache_path(file_path: Path) -> Path:
    """获取清洗结果缓存文件路径。"""
    cache_dir = OUTPUT_DIR / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{file_path.stem}_cleaned.json"


def _save_cleaned_cache(cache_path: Path, cleaned: list[CleanedChapter], title: str, author: str, language: str) -> None:
    """持久化清洗结果到 JSON。"""
    data = {
        "title": title,
        "author": author,
        "language": language,
        "chapters": [
            {"title": ch.title, "chunks": ch.chunks}
            for ch in cleaned
        ],
    }
    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"  清洗结果已缓存: {cache_path}")


def _load_cleaned_cache(cache_path: Path) -> tuple[str, str, str, list[CleanedChapter]] | None:
    """从缓存加载清洗结果，返回 (title, author, language, chapters) 或 None。"""
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        chapters = [CleanedChapter(title=ch["title"], chunks=ch["chunks"]) for ch in data["chapters"]]
        language = data.get("language", "zh")
        return data["title"], data["author"], language, chapters
    except Exception as e:
        logger.warning(f"  缓存加载失败: {e}")
        return None


async def process_book(file_path: Path) -> Path:
    """处理单本书，返回输出目录。支持增量处理。"""
    start = time.time()
    logger.info(f"开始处理: {file_path.name}")

    cache_path = _get_cache_path(file_path)

    # Phase 1: 解析
    logger.info("[1/4] 解析 EPUB...")
    book = parse_file(file_path)
    total_chunks = sum(len(ch.chunks) for ch in book.chapters)
    logger.info(f"  书名: {book.title}, 作者: {book.author}")
    logger.info(f"  章节数: {len(book.chapters)}, 文本块数: {total_chunks}")

    # Phase 2: 文本清洗（支持缓存恢复）
    cached = _load_cleaned_cache(cache_path)
    if cached:
        title, author, language, cleaned = cached
        logger.info(f"[2/4] 从缓存恢复清洗结果: {len(cleaned)} 章节")
    else:
        chapter_tuples = [(ch.title, ch.chunks) for ch in book.chapters]
        if CLEAN_MODE == "llm":
            logger.info("[2/4] LLM 清洗文本...")
            cleaned = await clean_chapters(chapter_tuples)
        else:
            logger.info("[2/4] 规则引擎清洗文本...")
            cleaned = rule_clean_chapters(chapter_tuples)
        _save_cleaned_cache(cache_path, cleaned, book.title, book.author, book.language)
        logger.info(f"  清洗完成: {len(cleaned)} 章节")
        title, author, language = book.title, book.author, book.language

    # Phase 3: TTS 合成（支持增量处理）
    output_dir = OUTPUT_DIR / _sanitize_dirname(title)
    existing_chapters = _get_existing_chapters(output_dir)

    if existing_chapters:
        logger.info(f"[3/4] TTS 语音合成 (语言: {language})... [增量模式]")
        logger.info(f"  已存在 {len(existing_chapters)} 个章节，跳过已处理的章节")
    else:
        logger.info(f"[3/4] TTS 语音合成 (语言: {language})...")

    # 只处理缺失的章节
    chapters_to_process = [
        (idx, ch) for idx, ch in enumerate(cleaned)
        if idx + 1 not in existing_chapters
    ]

    if not chapters_to_process:
        logger.info("  所有章节已处理完成，跳过 TTS 合成")
        chapter_audios = []
    else:
        logger.info(f"  需要处理 {len(chapters_to_process)} 个章节")
        chapter_audios = await synthesize_chapters(
            [ch for _, ch in chapters_to_process],
            language=language
        )
        # 恢复章节编号
        for i, (original_idx, _) in enumerate(chapters_to_process):
            chapter_audios[i].track_num = original_idx + 1

    audio_count = sum(len(ch.audio_chunks) for ch in chapter_audios)
    logger.info(f"  合成完成: {audio_count} 音频块")

    # Phase 4: 音频拼接
    logger.info("[4/4] 音频拼接与导出...")
    mp3_paths = assemble_book(chapter_audios, title, author, output_dir)
    logger.info(f"  导出完成: {len(mp3_paths)} 个 MP3 文件")

    elapsed = time.time() - start
    logger.info(f"处理完成! 耗时: {elapsed:.1f}s, 输出: {output_dir}")

    return output_dir


def _sanitize_dirname(name: str) -> str:
    """清理目录名中的非法字符。"""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def _get_existing_chapters(output_dir: Path) -> set[int]:
    """获取已存在的 MP3 文件对应的章节编号。"""
    if not output_dir.exists():
        return set()

    existing = set()
    for mp3_file in output_dir.glob("*.mp3"):
        # 从文件名提取章节编号，格式如 "01_章节标题.mp3"
        match = re.match(r"^(\d+)_", mp3_file.name)
        if match:
            existing.add(int(match.group(1)))
    return existing
