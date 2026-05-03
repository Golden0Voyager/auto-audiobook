"""音色选择器 — 终端交互界面。"""

from __future__ import annotations

import questionary
from rich.console import Console
from rich.table import Table

from text_processor import detect_language
from voice_profiles import CATEGORY_LABELS, VOICE_PROFILES, get_voice_description, get_voice_names

console = Console()


def select_voice(text: str | None = None) -> tuple[str, str, str]:
    """交互式音色选择，返回 (category, lang, voice_name)。"""
    # 第一步：选择内容类型
    category_label = questionary.select(
        "请选择内容类型:",
        choices=list(CATEGORY_LABELS.values()),
        style=questionary.Style([
            ('pointer', 'fg:#00ffff'),
            ('selected', 'fg:#00ff00'),
        ]),
    ).ask()

    if category_label is None:
        raise KeyboardInterrupt

    # 反查 category key
    category_key = {v: k for k, v in CATEGORY_LABELS.items()}[category_label]

    # 第二步：自动检测语言（如有文本）或让用户选择
    if text:
        lang = detect_language(text)
        lang_display = "中文" if lang == "zh" else "English"
        console.print(f"  检测到语言: {lang_display}")
    else:
        lang_choice = questionary.select(
            "请选择语言:",
            choices=["中文", "English"],
            style=questionary.Style([
                ('pointer', 'fg:#00ffff'),
                ('selected', 'fg:#00ff00'),
            ]),
        ).ask()
        lang = "zh" if lang_choice == "中文" else "en"

    # 第三步：选择具体音色
    voices = get_voice_names(category_key, lang)
    voice_name = questionary.select(
        "选择音色:",
        choices=voices,
        style=questionary.Style([
            ('pointer', 'fg:#00ffff'),
            ('selected', 'fg:#00ff00'),
        ]),
    ).ask()

    if voice_name is None:
        raise KeyboardInterrupt

    # 显示选择结果
    voice_desc = get_voice_description(category_key, lang, voice_name)
    console.print(f"\n[green]已选择: {category_label} / {'中文' if lang == 'zh' else 'English'} / {voice_name}[/green]")
    console.print(f"[dim]音色描述: {voice_desc[:50]}...[/dim]\n")

    return category_key, lang, voice_name


def display_voice_profiles() -> None:
    """显示所有可用的音色配置。"""
    table = Table(title="可用音色配置", border_style="cyan", show_header=True, header_style="bold magenta")
    table.add_column("场景", style="bold")
    table.add_column("语言")
    table.add_column("音色")
    table.add_column("描述", max_width=50)

    for category, lang_voices in VOICE_PROFILES.items():
        label = CATEGORY_LABELS.get(category, category)
        for lang, voices in lang_voices.items():
            lang_display = "中文" if lang == "zh" else "English"
            for voice_name, voice_desc in voices.items():
                desc_short = voice_desc[:47] + "..." if len(voice_desc) > 50 else voice_desc
                table.add_row(label, lang_display, voice_name, desc_short)

    console.print(table)
