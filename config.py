"""配置管理 — 路径、API、音频参数。"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)  # 强制从 .env 读取，覆盖系统环境变量

# === 路径 ===
BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
TTS_CACHE_DIR = OUTPUT_DIR / ".tts_cache"


def init_dirs() -> None:
    """延迟初始化目录，避免 import config 时产生副作用。"""
    INPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    TTS_CACHE_DIR.mkdir(exist_ok=True)

# === MiMo API ===
MIMO_API_KEY: str = os.environ.get("XIAOMI_MIMO_API_KEY", "")
MIMO_BASE_URL: str = os.environ.get("XIAOMI_MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_LLM_MODEL: str = "mimo-v2.5-pro"
MIMO_TTS_MODEL: str = "mimo-v2.5-tts"  # 标准 TTS 模型（长文本稳定）
MIMO_TTS_MODEL_VOICEDESIGN: str = "mimo-v2.5-tts-voicedesign"  # VoiceDesign 模型（保留作测试用）

# === TTS 参数 ===
TTS_VOICES: dict[str, str] = {
    "zh": "茉莉",    # 中文女声
    "en": "Mia",     # 英文女声
}

# 可用音色列表（供交互界面选择）
TTS_VOICE_OPTIONS: dict[str, list[dict[str, str]]] = {
    "zh": [
        {"name": "茉莉", "gender": "female", "label": "温柔女声，适合有声书、杂志"},
        {"name": "白桦", "gender": "male", "label": "沉稳男声，适合传记、财经"},
        {"name": "苏打", "gender": "male", "label": "活力男声，适合科技、新闻"},
        {"name": "冰糖", "gender": "female", "label": "甜美女声，适合小说、艺术"},
    ],
    "en": [
        {"name": "Mia", "gender": "female", "label": "Warm female, suitable for audiobooks"},
        {"name": "Milo", "gender": "male", "label": "Calm male, suitable for biography"},
        {"name": "Chloe", "gender": "female", "label": "Professional female, suitable for news"},
        {"name": "Dean", "gender": "male", "label": "Authoritative male, suitable for finance"},
    ],
}

# TTS 风格控制（放在 user message 中，支持自然语言描述）
# Why: MiMo TTS 通过 style prompt 控制语速，明确写入"语速偏慢"可显著降低朗读速度
TTS_STYLE_PRESETS: dict[str, dict[str, str]] = {
    "default": {
        "zh": "平静、清晰、温暖的朗读风格，语速偏慢，吐字清晰，句间停顿自然，适合长时间连续收听",
        "en": "Calm, clear, warm narration style, slow and deliberate pace, natural pauses between sentences, suitable for long listening sessions",
    },
    "news": {
        "zh": "专业播音员风格，字正腔圆，语气权威，语速适中偏慢，节奏稳重，适合新闻报道和财经分析",
        "en": "Professional news anchor style, clear articulation, authoritative tone, measured and steady pace, suitable for news and financial analysis",
    },
    "story": {
        "zh": "生动的故事叙述风格，富有感情，抑扬顿挫，语速舒缓，在对话和转折处适当停顿，适合小说和故事类内容",
        "en": "Vivid storytelling style, emotional, expressive intonation, slow and relaxed pace, with thoughtful pauses at dialogue and turning points, suitable for novels and stories",
    },
    "biography": {
        "zh": "客观平实的叙述风格，语气中性，语速偏慢，像历史纪录片旁白，沉稳庄重",
        "en": "Objective and neutral narration style, like a documentary narrator, slow and dignified pace, calm and solemn",
    },
    "nonfiction": {
        "zh": "专业清晰的讲解风格，逻辑感强，语速适中偏慢，重点处自然停顿，适合知识性内容",
        "en": "Professional and clear explanatory style, logical, moderate-to-slow pace, natural pauses at key points, suitable for educational content",
    },
}

# 当前使用的风格
TTS_STYLE: str = "default"
TTS_STYLES: dict[str, str] = TTS_STYLE_PRESETS["default"]
TTS_AUDIO_FORMAT: str = "wav"

# === 音频输出 ===
MP3_BITRATE: str = "256k"
MP3_CHANNELS: int = 1
CHAPTER_SILENCE_MS: int = 1500

# === 并发控制 ===
LLM_CONCURRENCY: int = int(os.environ.get("LLM_CONCURRENCY", "5"))
TTS_CONCURRENCY: int = int(os.environ.get("TTS_CONCURRENCY", "24"))

# === 文本分块 ===
CHUNK_MAX_CHARS: int = 600  # 软限制：优先在此附近找自然边界切分
CHUNK_HARD_LIMIT: int = 900  # 硬限制：任何 chunk 不允许超过此长度

# === 重试 ===
MAX_RETRIES: int = 3
RETRY_BASE_DELAY: float = 2.0

# === 清洗模式 ===
CLEAN_MODE: str = "rule"  # "rule" 或 "llm"
