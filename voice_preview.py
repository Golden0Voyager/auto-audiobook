"""语音试听脚本 — 快速生成样例音频，用于选择和优化音色。"""

import asyncio
import base64
import os
import sys

from openai import AsyncOpenAI

MIMO_API_KEY = os.environ.get("XIAOMI_MIMO_API_KEY", "")
MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"

# 可用中文音色
VOICES = {
    "冰糖": "中文女声，温暖清晰",
    "茉莉": "中文女声",
    "苏打": "中文男声",
    "白桦": "中文男声",
}

SAMPLE_TEXT = "在那遥远的地方，有一个古老的村庄。清晨的阳光穿过薄雾，洒在青石板路上。远处传来几声犬吠，伴随着炊烟袅袅升起。这是一个宁静而美好的早晨。"

STYLE_PROMPTS = {
    "平静朗读": "平静、清晰、温暖的朗读风格，语速适中，适合长时间连续收听",
    "新闻播报": "专业、稳重的新闻播报风格，吐字清晰，节奏均匀",
    "故事讲述": "生动、富有感情的故事讲述风格，适当加入语气变化",
    "低声耳语": "轻柔、亲密的耳语风格，像在耳边轻声细语",
}


async def generate_sample(voice: str, style_name: str, style_prompt: str, output_dir: str) -> str:
    """生成单个音色样例。"""
    client = AsyncOpenAI(api_key=MIMO_API_KEY, base_url=MIMO_BASE_URL)

    response = await client.chat.completions.create(
        model="mimo-v2.5-tts",
        messages=[
            {"role": "user", "content": style_prompt},
            {"role": "assistant", "content": SAMPLE_TEXT},
        ],
        audio={"format": "wav", "voice": voice},
    )

    message = response.choices[0].message
    if message.audio and message.audio.data:
        audio_bytes = base64.b64decode(message.audio.data)
        filename = f"{voice}_{style_name}.wav"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "wb") as f:
            f.write(audio_bytes)
        return filepath
    return ""


async def main() -> None:
    output_dir = "voice_samples"
    os.makedirs(output_dir, exist_ok=True)

    print("=== MiMo V2.5 TTS 语音试听 ===\n")
    print(f"样例文本: {SAMPLE_TEXT}\n")

    if "--all" in sys.argv:
        # 生成所有音色 + 所有风格的组合
        tasks = []
        for voice, desc in VOICES.items():
            for style_name, style_prompt in STYLE_PROMPTS.items():
                tasks.append(generate_sample(voice, style_name, style_prompt, output_dir))
                print(f"生成中: {voice} / {style_name} ({desc})")

        results = await asyncio.gather(*tasks)
        print(f"\n完成! 共生成 {len([r for r in results if r])} 个样例")
    else:
        # 默认只生成冰糖 + 平静朗读
        voice = "冰糖"
        style_name = "平静朗读"
        style_prompt = STYLE_PROMPTS[style_name]
        print(f"生成中: {voice} / {style_name}")
        path = await generate_sample(voice, style_name, style_prompt, output_dir)
        if path:
            print(f"完成! 样例已保存: {path}")

    print(f"\n样例目录: {output_dir}/")
    print("用 VLC 或其他播放器打开试听")
    print("\n可用音色:")
    for voice, desc in VOICES.items():
        print(f"  {voice}: {desc}")
    print("\n可用风格:")
    for name, prompt in STYLE_PROMPTS.items():
        print(f"  {name}: {prompt}")
    print("\n用法:")
    print("  python voice_preview.py          # 生成冰糖/平静朗读样例")
    print("  python voice_preview.py --all    # 生成所有音色+风格组合")


if __name__ == "__main__":
    asyncio.run(main())
