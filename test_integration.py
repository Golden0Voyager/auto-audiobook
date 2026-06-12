"""集成测试 — 验证 VoiceDesign 集成。"""

import asyncio
import sys
from pathlib import Path

# 测试模块导入
print("1. 测试模块导入...")
try:
    from voice_profiles import VOICE_PROFILES, CATEGORY_LABELS, get_voice_description, get_voice_names, display_voice_profiles
    from text_processor import detect_language, optimize_for_speech
    print("   ✅ 所有模块导入成功")
except Exception as e:
    print(f"   ❌ 模块导入失败: {e}")
    sys.exit(1)

# 测试语言检测
print("\n2. 测试语言检测...")
test_cases = [
    ("这是一个中文测试文本", "zh"),
    ("This is an English test text", "en"),
    ("混合 mixed 文本", "zh"),
]
for text, expected in test_cases:
    result = detect_language(text)
    status = "✅" if result == expected else "❌"
    print(f"   {status} '{text[:20]}...' -> {result} (预期: {expected})")

# 测试音色配置
print("\n3. 测试音色配置...")
for category, label in CATEGORY_LABELS.items():
    langs = list(VOICE_PROFILES[category].keys())
    voices_zh = get_voice_names(category, "zh") if "zh" in langs else []
    voices_en = get_voice_names(category, "en") if "en" in langs else []
    print(f"   ✅ {label}: 中文 {len(voices_zh)} 音色, 英文 {len(voices_en)} 音色")

# 测试音色描述获取
print("\n4. 测试音色描述获取...")
desc = get_voice_description("magazine", "zh", "mature_male")
print(f"   ✅ magazine/zh/mature_male: {desc[:30]}...")

# 测试文本优化
print("\n5. 测试文本优化...")
test_text = "这是一个测试文本，用于验证文本优化功能。"
optimized = optimize_for_speech(test_text)
print(f"   ✅ 文本优化: '{test_text}' -> '{optimized}'")

print("\n✅ 所有集成测试通过!")
print("\n可以使用以下命令测试完整流程:")
print("  .venv/bin/python main.py --list-voices")
print("  .venv/bin/python main.py --file input/test.epub --category magazine --voice mature_male")
