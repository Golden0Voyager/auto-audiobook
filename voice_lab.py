"""试听对比室 — 批量合成多组合，让用户横向比较音色与风格。"""
from __future__ import annotations

import asyncio
import logging
import platform
import random
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import questionary
from rich.console import Console
from rich.table import Table

import config
from assembler import _concat_wav_chunks, export_to_mp3
from models import BookData
from parser import parse_file
from rule_cleaner import clean_chapters as rule_clean
from synthesizer import synthesize_chapters

logger = logging.getLogger(__name__)
console = Console()


def _play_mp3(path: Path) -> None:
    """跨平台播放 MP3 文件。播放器缺失时打印警告并返回。"""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["afplay", str(path)], check=False)
        elif system == "Linux":
            subprocess.run(["mpg123", "-q", str(path)], check=False)
        elif system == "Windows":
            subprocess.run(["start", str(path)], shell=True, check=False)
        else:
            logger.warning(f"暂不支持在当前系统播放音频: {system}")
    except FileNotFoundError as e:
        logger.warning(f"播放器不可用 ({e}); 文件位于: {path}")


@dataclass
class PreviewItem:
    voice: str
    style: str
    style_label: str
    mp3_path: Path | None
    error: str | None
    duration_sec: float

_SENTENCE_END = re.compile(r'[。！？!?\.](?=[^"」』]|$)')


def _truncate_at_sentence(text: str, target: int) -> str:
    """在 [target*0.7, target*1.3] 区间内寻找最近句末标点截断。

    无合适标点时硬截断到 target。
    """
    if len(text) <= target:
        return text
    window = text[: int(target * 1.3)]
    cuts = [m.end() for m in _SENTENCE_END.finditer(window)]
    cuts = [c for c in cuts if c >= target * 0.7]
    if cuts:
        return text[: cuts[0]]
    return text[:target]


def _sample_preview_text(book: BookData, target_chars: int = 200) -> str:
    """从书中智能抽取一段试听文本。

    规则：
    1. 过滤"目录式"章节（标题<=2字 或 章节总文本<=200字）
    2. 全部被过滤则回退到原始章节列表
    3. 随机选一章；最多重抽 3 次以避开 chunks 为空的章节
    4. 取首个 chunk 在自然边界截断到 ~target_chars
    5. 不足 50 字时,拼接同章后续 chunk（不修改原对象）
    """
    content_chapters = [
        ch for ch in book.chapters
        if len(ch.title) > 2 and sum(len(c) for c in ch.chunks) > 200
    ]
    if not content_chapters:
        content_chapters = book.chapters

    chapter = None
    for _ in range(3):
        candidate = random.choice(content_chapters)
        if candidate.chunks:
            chapter = candidate
            break
    if chapter is None:
        return ""

    text = _truncate_at_sentence(chapter.chunks[0], target_chars)

    idx = 1
    while len(text) < 50 and idx < len(chapter.chunks):
        text += chapter.chunks[idx][: target_chars - len(text)]
        idx += 1
    return text


# 与 main.py 的 STYLE_LABELS 同步；voice_lab 独立声明避免循环依赖
_STYLE_LABELS_ZH = {
    "default": "默认（平静温暖）",
    "news": "新闻播报（权威专业）",
    "story": "故事叙述（富有感情）",
    "biography": "传记叙述（客观平实）",
    "nonfiction": "知识讲解（清晰逻辑）",
}
_STYLE_LABELS_EN = {
    "default": "Default (calm & warm)",
    "news": "News (authoritative)",
    "story": "Story (emotional)",
    "biography": "Biography (objective)",
    "nonfiction": "Non-fiction (clear logic)",
}


def _style_labels(language: str) -> dict[str, str]:
    return _STYLE_LABELS_EN if language == "en" else _STYLE_LABELS_ZH


def _select_combos(language: str) -> list[tuple[str, str]]:
    """让用户勾选 (voice, style) 组合。返回选定的列表。

    默认勾选：当前语言下所有音色 × 'default' 风格。
    超 20 个时弹 confirm 防误操作（软提示，不强阻断）。
    """
    voices = config.TTS_VOICE_OPTIONS.get(language, config.TTS_VOICE_OPTIONS["zh"])
    styles = _style_labels(language)

    choices = []
    for v in voices:
        for style_key, style_label in styles.items():
            title = f"{v['name']} × {style_label}"
            checked = (style_key == "default")
            choices.append(
                questionary.Choice(
                    title=title,
                    value=(v["name"], style_key),
                    checked=checked,
                )
            )

    selected = questionary.checkbox(
        "勾选要试听的 (音色 × 风格) 组合（空格选/取消，回车确认）：",
        choices=choices,
    ).ask() or []

    if len(selected) > 20:
        ok = questionary.confirm(
            f"勾选 {len(selected)} 个组合，预计耗时 ~{len(selected) * 3} 秒，确认？",
            default=True,
        ).ask()
        if not ok:
            return []

    return list(selected)


async def _synthesize_one(
    text: str,
    language: str,
    voice: str,
    style_key: str,
    style_label: str,
    out_path: Path,
    lock: asyncio.Lock,
) -> PreviewItem:
    """合成一个组合 → 临时 mp3。失败时返回带 error 的 PreviewItem。"""
    cleaned = rule_clean([("preview", [text])])
    async with lock:
        original_voice = config.TTS_VOICES.get(language)
        original_styles = config.TTS_STYLES
        config.TTS_VOICES[language] = voice
        config.TTS_STYLES = config.TTS_STYLE_PRESETS[style_key]
        try:
            try:
                chapter_audios, _ = await synthesize_chapters(cleaned, language=language)
            except Exception as e:
                return PreviewItem(
                    voice=voice, style=style_key, style_label=style_label,
                    mp3_path=None, error=f"{type(e).__name__}: {e}", duration_sec=0.0,
                )
        finally:
            if original_voice is not None:
                config.TTS_VOICES[language] = original_voice
            config.TTS_STYLES = original_styles

    if not chapter_audios or not chapter_audios[0].audio_chunks:
        return PreviewItem(
            voice=voice, style=style_key, style_label=style_label,
            mp3_path=None, error="empty audio", duration_sec=0.0,
        )

    combined = _concat_wav_chunks(chapter_audios[0].audio_chunks)
    duration = len(combined) / 1000.0
    export_to_mp3(combined, out_path)
    return PreviewItem(
        voice=voice, style=style_key, style_label=style_label,
        mp3_path=out_path, error=None, duration_sec=duration,
    )


async def _synthesize_previews(
    text: str,
    language: str,
    combos: list[tuple[str, str]],
    tmp_dir: Path,
) -> list[PreviewItem]:
    """合成所有组合（每个 synthesize_chapters 内部仍并发，外部用 lock 串行化避免 config 写争抢）。"""
    labels = _style_labels(language)
    lock = asyncio.Lock()
    tasks = []
    for voice, style_key in combos:
        out_path = tmp_dir / f"preview_{voice}_{style_key}.mp3"
        tasks.append(
            _synthesize_one(
                text, language, voice, style_key,
                labels.get(style_key, style_key), out_path, lock,
            )
        )
    return await asyncio.gather(*tasks)


def _render_table(items: list[PreviewItem], current: int | None) -> None:
    """打印对比室表格。current 为当前候选的索引（0-based），可为 None。"""
    table = Table(
        title="试听对比室",
        border_style="cyan",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("音色")
    table.add_column("风格")
    table.add_column("状态")
    table.add_column("时长")
    table.add_column("候选", justify="center")

    for idx, it in enumerate(items):
        if it.error:
            status = f"[red]✗ {it.error[:20]}[/red]"
            duration = "-"
        else:
            status = "[green]✓ 已生成[/green]"
            duration = f"{it.duration_sec:.1f}s"
        marker = "[yellow]★[/yellow]" if current == idx else ""
        table.add_row(
            str(idx + 1), it.voice, it.style_label, status, duration, marker,
        )

    console.print(table)


async def _interactive_compare(
    items: list[PreviewItem], language: str,
) -> tuple[str, str]:
    """菜单循环：选听 / 设候选 / 确认。返回 (voice, style)。

    退出（Ctrl+C / 取消）会抛 KeyboardInterrupt，由调用方决定回退。
    """
    current = next(
        (i for i, it in enumerate(items) if it.error is None),
        None,
    )
    if current is None:
        console.print("[yellow]全部试听合成失败，使用默认配置继续[/yellow]")
        return (
            config.TTS_VOICES.get(language, "茉莉"),
            "default",
        )

    while True:
        _render_table(items, current)
        cur_item = items[current]
        console.print(
            f"[cyan]当前候选：#{current + 1} {cur_item.voice} × {cur_item.style_label}[/cyan]"
        )

        action = await questionary.select(
            "下一步操作：",
            choices=[
                questionary.Choice(title="▶ 试听某个编号", value="play"),
                questionary.Choice(title="★ 设某个编号为候选", value="pick"),
                questionary.Choice(title="✓ 确认当前候选并继续", value="confirm"),
                questionary.Choice(title="✗ 取消（用默认音色/风格）", value="cancel"),
            ],
        ).unsafe_ask_async()

        if action == "confirm":
            return (cur_item.voice, cur_item.style)

        if action == "cancel":
            return (
                config.TTS_VOICES.get(language, "茉莉"),
                "default",
            )

        if action in ("play", "pick"):
            playable_indices = [
                str(i + 1) for i, it in enumerate(items) if it.error is None
            ]
            num_str = await questionary.select(
                "选择编号:",
                choices=playable_indices,
            ).unsafe_ask_async()
            n = int(num_str) - 1
            if action == "play":
                console.print(
                    f"[cyan]播放 #{n + 1} ({items[n].duration_sec:.1f}s)...[/cyan]"
                )
                _play_mp3(items[n].mp3_path)
            else:  # pick
                current = n
                console.print(f"[green]候选已切换到 #{n + 1}[/green]")


async def run_voice_lab(file_path: Path, language: str) -> tuple[str, str]:
    """试听对比室入口。返回最终选定的 (voice, style)。

    任意失败均回退到 (默认音色, 'default')，不阻塞主流程。
    """
    default_voice = config.TTS_VOICES.get(language, "茉莉")
    default_fallback = (default_voice, "default")

    try:
        book = parse_file(file_path)
    except Exception as e:
        console.print(f"[yellow]试听准备失败: {e}，使用默认配置继续[/yellow]")
        return default_fallback

    text = _sample_preview_text(book, target_chars=200)
    if not text:
        console.print("[yellow]无法抽取试听文本，使用默认配置继续[/yellow]")
        return default_fallback

    preview_clip = text[:80] + "…" if len(text) > 80 else text
    console.print(f"[dim]试听文本: {preview_clip}[/dim]")

    combos = _select_combos(language)
    if not combos:
        console.print("[yellow]未勾选任何组合，使用默认配置继续[/yellow]")
        return default_fallback

    tmp_dir = Path(tempfile.mkdtemp(prefix="voice_lab_"))
    try:
        console.print(f"[cyan]开始合成 {len(combos)} 个试听片段…[/cyan]")
        items = await _synthesize_previews(text, language, combos, tmp_dir)
        try:
            return await _interactive_compare(items, language)
        except KeyboardInterrupt:
            console.print("[yellow]已取消试听，使用默认配置继续[/yellow]")
            return default_fallback
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)




