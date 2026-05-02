"""配置管理 — 路径、API、音频参数。"""

import os
from pathlib import Path

# === 路径 ===
BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

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
TTS_STYLES: dict[str, str] = {
    "zh": "平静、清晰、温暖的朗读风格，语速适中，适合长时间连续收听",
    "en": "Calm, clear, warm narration style, moderate pace, suitable for long listening sessions",
}
TTS_AUDIO_FORMAT: str = "wav"

# === 音频输出 ===
MP3_BITRATE: str = "256k"
MP3_CHANNELS: int = 1
CHAPTER_SILENCE_MS: int = 1500

# === 并发控制 ===
LLM_CONCURRENCY: int = 5
TTS_CONCURRENCY: int = 5

# === 文本分块 ===
CHUNK_MAX_CHARS: int = 1500

# === 重试 ===
MAX_RETRIES: int = 3
RETRY_BASE_DELAY: float = 2.0

# === 清洗模式 ===
CLEAN_MODE: str = "rule"  # "rule" 或 "llm"
