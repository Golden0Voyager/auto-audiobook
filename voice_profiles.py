"""音色库 — 按场景和语言组织的 VoiceDesign 音色描述。"""

VOICE_PROFILES: dict[str, dict[str, dict[str, str]]] = {
    # === 杂志文章播报 ===
    "magazine": {
        "zh": {
            "mature_male": "一位成熟稳重的中年男性播音员，声音浑厚有磁性，语速沉稳从容，吐字清晰圆润，带有知识分子的儒雅气质，如同《收获》杂志的资深主播在深夜为你朗读一篇深度报道，语气平和但富有洞察力",
            "warm_female": "一位气质温婉的女性播音员，声音清澈柔和，语速舒缓自然，咬字清晰但不生硬，像一位博学的闺蜜在午后咖啡馆与你分享一篇精彩长文，娓娓道来，引人入胜",
        },
        "en": {
            "articulate_male": "A distinguished male narrator with a rich, resonant voice and a measured, deliberate pace, embodying the intellectual gravitas of a seasoned Atlantic correspondent delivering a compelling long-form feature, speaking with clarity and thoughtful authority",
            "engaging_female": "A warm and articulate female narrator with a clear, melodious voice, delivering content with the easy confidence of a New Yorker staff writer sharing an insightful essay, natural pacing, sophisticated yet approachable",
        },
    },

    # === 有声书 - 传记 ===
    "audiobook_biography": {
        "zh": {
            "storyteller_male": "一位声音温和的中年男性讲述者，语速平稳适中，语气客观平实，像一位历史纪录片的旁白，娓娓道来但不过分渲染情感，保持中性的叙述态度",
            "gentle_female": "一位声音柔和的女性讲述者，语速舒缓自然，语气平和客观，像一位传记作家在平静地讲述一个人的一生，情感表达克制但不冷漠",
        },
        "en": {
            "narrator_male": "A male narrator with a warm but neutral tone, steady and measured pace, objective delivery like a documentary narrator, telling life stories with restrained emotion and factual clarity",
            "narrator_female": "A female narrator with a gentle but composed voice, natural pacing, objective and balanced tone, like a biographer calmly recounting a person's life journey with measured emotion",
        },
    },

    # === 有声书 - 非小说 ===
    "audiobook_nonfiction": {
        "zh": {
            "professional_male": "一位专业的男性播音员，声音清晰有力，语速适中，逻辑感强，适合社科、商业类非虚构内容",
            "analytical_female": "一位理性的女性解说，声音干练清晰，条理分明，适合科普、心理学等知识性内容",
        },
        "en": {
            "informative_male": "An informative male narrator, clear and authoritative, moderate pace, suitable for non-fiction and social sciences",
            "engaging_female": "An engaging female narrator, articulate and accessible, suitable for popular science and psychology",
        },
    },

    # === 有声书 - 文史哲 ===
    "audiobook_literature": {
        "zh": {
            "classic_male": "一位富有学识的男性讲述者，声音深沉有韵味，语速偏慢，适合历史、哲学、文学评论等严肃内容",
            "scholarly_female": "一位儒雅的女性学者型讲述者，声音温润知性，节奏从容，适合文史哲类深度内容",
        },
        "en": {
            "literary_male": "A literary male narrator with a measured, thoughtful pace, deep and contemplative, suitable for philosophy and history",
            "elegant_female": "An elegant female narrator with intellectual depth, graceful and composed, suitable for literary criticism and humanities",
        },
    },

    # === 有声书 - 小说 ===
    "audiobook_fiction": {
        "zh": {
            "gentle_female": "一位温柔的年轻女性讲述者，声音细腻富有感情，语速舒缓，适合中文小说的情感表达",
            "storyteller_male": "一位沉稳的中年男性讲述者，声音富有磁性，抑扬顿挫，适合悬疑、历史类中文小说",
        },
        "en": {
            "warm_female": "A warm, articulate female narrator with a natural American accent, moderate pace, suitable for fiction",
            "dramatic_male": "A deep-voiced male narrator with rich intonation, slightly slower pace, suitable for dramatic fiction",
        },
    },

    # === 有声书 - 艺术类 ===
    "audiobook_art": {
        "zh": {
            "elegant_female": "一位优雅的女性讲述者，声音柔和有艺术气质，语速舒缓，富有美感，适合艺术、设计、美学类内容",
            "cultured_male": "一位有文化底蕴的男性讲述者，声音温润从容，品味感强，适合艺术史、博物馆导览类内容",
        },
        "en": {
            "refined_female": "A refined female narrator with aesthetic sensibility, gentle and eloquent, suitable for art and design content",
            "cultured_male": "A cultured male narrator with artistic appreciation, warm and knowledgeable, suitable for art history",
        },
    },

    # === 财经新闻播讲 ===
    "finance": {
        "zh": {
            "professional_male": "财经新闻男主播，声音洪亮有力，吐字清晰干脆，语速适中略快，带有明显的播报腔调和节奏感，语气自信果断，每个字都掷地有声，像正在直播的财经节目主持人，专业权威但不沉闷",
            "analytical_female": "财经分析女主播，声音清脆利落，语速平稳流畅，逻辑清晰，表达简洁有力，像一位资深财经评论员在做市场分析，理性客观但不失亲和力",
        },
        "en": {
            "authoritative_male": "Professional male financial news anchor, clear and assertive delivery, brisk but measured pace, confident and authoritative tone, crisp articulation with natural broadcast rhythm, like a live financial news host",
            "insightful_female": "Professional female financial analyst, clear and precise delivery, steady and fluent pace, logical and concise expression, like a seasoned market commentator providing insightful analysis",
        },
    },

    # === 科技类内容 ===
    "tech": {
        "zh": {
            "young_male": "一位年轻的男性科技主播，声音清亮有活力，语速稍快，富有科技感和未来感，适合科技新闻和产品评测",
            "calm_female": "一位冷静的女性科技解说，声音清晰理性，语速平稳，条理分明，适合技术深度分析和教程",
        },
        "en": {
            "dynamic_male": "A dynamic male tech narrator, energetic and forward-looking, slightly faster pace, suitable for tech news and reviews",
            "clear_female": "A clear-headed female narrator, precise and informative, moderate pace, suitable for technical analysis and tutorials",
        },
    },
}

CATEGORY_LABELS: dict[str, str] = {
    "magazine": "杂志文章播报",
    "audiobook_biography": "有声书 - 传记",
    "audiobook_nonfiction": "有声书 - 非小说",
    "audiobook_literature": "有声书 - 文史哲",
    "audiobook_fiction": "有声书 - 小说",
    "audiobook_art": "有声书 - 艺术类",
    "finance": "财经新闻播讲",
    "tech": "科技类内容",
}


def get_voice_names(category: str, lang: str) -> list[str]:
    """获取某场景某语言下所有可用音色名称。"""
    return list(VOICE_PROFILES.get(category, {}).get(lang, {}).keys())


def get_voice_description(category: str, lang: str, voice_name: str) -> str:
    """获取指定音色的描述文本。"""
    return VOICE_PROFILES.get(category, {}).get(lang, {}).get(voice_name, "")


def display_voice_profiles() -> None:
    """显示所有可用的音色配置。"""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()

    # 标准 TTS 模型预设音色
    console.print(Panel("[bold cyan]可用音色 (mimo-v2.5-tts)[/bold cyan]", border_style="cyan"))

    table = Table(title="预设音色", border_style="green", show_header=True, header_style="bold magenta")
    table.add_column("语言", style="cyan", width=6)
    table.add_column("音色名称", style="green")
    table.add_column("说明")

    voices = {
        "zh": [
            ("茉莉", "温柔女声，适合有声书、杂志"),
            ("苏打", "活力男声，适合科技、新闻"),
            ("白桦", "沉稳男声，适合传记、财经"),
            ("冰糖", "甜美女声，适合小说、艺术"),
        ],
        "en": [
            ("Mia", "Warm female, suitable for audiobooks"),
            ("Chloe", "Professional female, suitable for news"),
            ("Milo", "Calm male, suitable for biography"),
            ("Dean", "Authoritative male, suitable for finance"),
        ],
    }

    for lang in ["zh", "en"]:
        lang_name = "中文" if lang == "zh" else "英文"
        for voice_name, description in voices[lang]:
            table.add_row(lang_name, voice_name, description)

    console.print(table)
