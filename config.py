"""配置管理 — 路径、API、音频参数。"""

import os
from pathlib import Path

# === 路径 ===
BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
TTS_CACHE_DIR = OUTPUT_DIR / ".tts_cache"
INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
TTS_CACHE_DIR.mkdir(exist_ok=True)

# === MiMo API ===
MIMO_API_KEY: str = os.environ.get("XIAOMI_MIMO_API_KEY", "")
MIMO_BASE_URL: str = "https://token-plan-cn.xiaomimimo.com/v1"
MIMO_LLM_MODEL: str = "mimo-v2.5-pro"
MIMO_TTS_MODEL: str = "mimo-v2.5-tts"

# === TTS 参数 ===
TTS_VOICES: dict[str, str] = {
    "zh": "茉莉",    # 中文女声
    "en": "Mia",     # 英文女声
}

# TTS 风格预设
TTS_STYLE_PRESETS: dict[str, dict[str, str]] = {
    "default": {
        "zh": "平静、清晰、温暖的朗读风格，语速适中，适合长时间连续收听",
        "en": "Calm, clear, warm narration style, moderate pace, suitable for long listening sessions",
    },
    "news": {
        "zh": "专业播音员风格，字正腔圆，语气权威，适合新闻报道和财经分析",
        "en": "Professional news anchor style, clear articulation, authoritative tone, suitable for news and financial analysis",
    },
    "story": {
        "zh": "生动的故事叙述风格，富有感情，抑扬顿挫，适合小说和故事类内容",
        "en": "Vivid storytelling style, emotional, expressive intonation, suitable for novels and stories",
    },
    "casual": {
        "zh": "轻松自然的对话风格，亲切温和，语速稍快，适合散文和随笔",
        "en": "Casual conversational style, warm and friendly, slightly faster pace, suitable for essays and casual writing",
    },
    "classic": {
        "zh": "经典朗读风格，节奏感强，有韵律感，适合经典文学和诗词",
        "en": "Classic reading style, strong rhythm, poetic feel, suitable for classical literature and poetry",
    },
}

# 当前使用的风格（默认为 "default"）
TTS_STYLE: str = "default"

# 兼容旧代码
TTS_STYLES: dict[str, str] = TTS_STYLE_PRESETS["default"]
TTS_AUDIO_FORMAT: str = "wav"

# === 音频输出 ===
MP3_BITRATE: str = "256k"
MP3_CHANNELS: int = 1
CHAPTER_SILENCE_MS: int = 1500

# === 并发控制 ===
LLM_CONCURRENCY: int = 5
TTS_CONCURRENCY: int = 25

# === 文本分块 ===
CHUNK_MAX_CHARS: int = 3000

# === 重试 ===
MAX_RETRIES: int = 3
RETRY_BASE_DELAY: float = 2.0

# === 清洗模式 ===
CLEAN_MODE: str = "rule"  # "rule" 或 "llm"
