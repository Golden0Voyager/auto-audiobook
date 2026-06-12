"""主流水线 — 串接 parser → cleaner → synthesizer → assembler。"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from pathlib import Path

import config
from assembler import assemble_book
from cleaner import clean_chapters
from models import ChapterAudio, CleanedChapter
from mutagen.mp3 import MP3
from parser import parse_file
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rule_cleaner import clean_chapters as rule_clean_chapters
from synthesizer import SynthesisStats, synthesize_chapters
from text_processor import detect_language

logger = logging.getLogger(__name__)
console = Console()


def _print_summary(
    title: str,
    elapsed: float,
    total_chars: int,
    total_duration_ms: int,
    mp3_count: int,
    tts_stats: SynthesisStats,
    output_dir: Path,
) -> None:
    """用 rich 面板输出处理完成总结。"""
    duration_sec = total_duration_ms / 1000
    duration_str = (
        f"{int(duration_sec // 3600)}:{int((duration_sec % 3600) // 60):02d}:{int(duration_sec % 60):02d}"
        if duration_sec >= 3600
        else f"{int(duration_sec // 60):02d}:{int(duration_sec % 60):02d}"
    )

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column(style="green")

    table.add_row("书名", title)
    table.add_row("总字数", f"{total_chars:,}")
    table.add_row("处理用时", f"{elapsed:.1f}s")
    table.add_row("可播放时长", duration_str)
    table.add_row("生成文件", f"{mp3_count} 个 MP3")
    table.add_row("TTS 缓存命中", f"{tts_stats.cache_hits}")
    table.add_row("TTS API 调用", f"{tts_stats.api_calls}")
    if tts_stats.failed_chunks > 0:
        table.add_row("[red]TTS 失败块[/red]", f"[red]{tts_stats.failed_chunks}[/red]")

    panel = Panel(
        table,
        title="[bold green]处理完成[/bold green]",
        border_style="green",
        subtitle=f"[dim]{output_dir}[/dim]",
    )
    console.print(panel)


def _get_cache_path(file_path: Path) -> Path:
    """获取清洗结果缓存文件路径。"""
    cache_dir = config.OUTPUT_DIR / ".cache"
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


async def process_book(file_path: Path, preview_chunks: int = 0) -> Path:
    """处理单本书，返回输出目录。支持增量处理和试听模式。"""
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
        if config.CLEAN_MODE == "llm":
            logger.info("[2/4] LLM 清洗文本...")
            cleaned = await clean_chapters(chapter_tuples)
        else:
            logger.info("[2/4] 规则引擎清洗文本...")
            cleaned = rule_clean_chapters(chapter_tuples)
        _save_cleaned_cache(cache_path, cleaned, book.title, book.author, book.language)
        logger.info(f"  清洗完成: {len(cleaned)} 章节")
        title, author, language = book.title, book.author, book.language

    # 统计字数
    total_chars = sum(len(chunk) for ch in cleaned for chunk in ch.chunks)

    # 试听模式：截取前 N 个文本块
    if preview_chunks > 0:
        cleaned = _truncate_to_chunks(cleaned, preview_chunks)
        logger.info(f"  试听模式: 截取前 {preview_chunks} 个文本块")

    # Phase 3: TTS 合成（支持增量处理）
    output_dir = config.OUTPUT_DIR / _build_output_dirname(file_path, title)
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

    tts_stats = SynthesisStats(total_chunks=0, cache_hits=0, api_calls=0, failed_chunks=0)
    if not chapters_to_process:
        logger.info("  所有章节已处理完成，跳过 TTS 合成")
        chapter_audios = []
    else:
        logger.info(f"  需要处理 {len(chapters_to_process)} 个章节")
        chapter_audios, tts_stats = await synthesize_chapters(
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
    mp3_paths, total_duration_ms = assemble_book(chapter_audios, title, author, output_dir)
    logger.info(f"  导出完成: {len(mp3_paths)} 个 MP3 文件")

    # 增量模式下已有 MP3 不会被 assemble_book 重新统计，补充扫描
    if not mp3_paths and existing_chapters:
        mp3_paths = sorted(output_dir.glob("*.mp3"))
        total_duration_ms = 0
        for p in mp3_paths:
            try:
                audio = MP3(str(p))
                total_duration_ms += int(audio.info.length * 1000)
            except Exception:
                pass
        logger.info(f"  检测到已有 {len(mp3_paths)} 个 MP3 文件")

    elapsed = time.time() - start

    # 显示完成总结面板
    _print_summary(
        title=title,
        elapsed=elapsed,
        total_chars=total_chars,
        total_duration_ms=total_duration_ms,
        mp3_count=len(mp3_paths),
        tts_stats=tts_stats,
        output_dir=output_dir,
    )

    # 将源文件复制到输出目录（保留原文件，避免破坏性操作）
    try:
        dest = output_dir / file_path.name
        if not dest.exists():
            shutil.copy2(str(file_path), str(dest))
            logger.info(f"  源文件已复制到: {dest}")
    except Exception as e:
        logger.warning(f"  源文件复制失败: {e}")

    return output_dir


def _truncate_to_chunks(chapters: list[CleanedChapter], max_chunks: int) -> list[CleanedChapter]:
    """截取前 N 个文本块。"""
    result: list[CleanedChapter] = []
    remaining = max_chunks
    for ch in chapters:
        if remaining <= 0:
            break
        truncated_chunks = ch.chunks[:remaining]
        result.append(CleanedChapter(title=ch.title, chunks=truncated_chunks))
        remaining -= len(truncated_chunks)
    return result


def _build_output_dirname(file_path: Path, title: str) -> str:
    """构建输出目录名。优先从文件名提取日期和期号，如 2026年04月27日-第16期。"""
    # 尝试匹配文件名中的日期和期号：2026年04月27日 (第16期)
    match = re.search(r"(\d{4}年\d{2}月\d{2}日)\s*\(第(\d+)期\)", file_path.stem)
    if match:
        return _sanitize_dirname(f"{match.group(1)}-第{match.group(2)}期")
    return _sanitize_dirname(title)


def _sanitize_dirname(name: str) -> str:
    """清理目录名中的非法字符。"""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def _get_existing_chapters(output_dir: Path) -> set[int]:
    """获取已完成的 MP3 章节编号。文件存在但损坏的会重制，避免断点续传卡死。"""
    if not output_dir.exists():
        return set()

    existing = set()
    for mp3_file in output_dir.glob("*.mp3"):
        # 从文件名提取章节编号，格式如 "01_章节标题.mp3"
        match = re.match(r"^(\d+)_", mp3_file.name)
        if not match:
            continue

        # 校验 MP3 是否有效（非空、可解析）
        try:
            audio = MP3(str(mp3_file))
            if audio.info.length <= 0:
                continue
        except Exception:
            continue

        existing.add(int(match.group(1)))
    return existing
