"""批量生成音色 sample 供试听。"""

import asyncio
import base64
import sys
from pathlib import Path

from openai import AsyncOpenAI
from voice_profiles import VOICE_PROFILES, CATEGORY_LABELS

# API 配置
API_KEY = "sk-cuv9q06gjejujnkmc5mdc6cyvphyn67wp74iflwq80uv8s7y"
BASE_URL = "https://api.xiaomimimo.com/v1"
MODEL = "mimo-v2.5-tts-voicedesign"

# 各场景专用测试文本
TEST_TEXTS: dict[str, dict[str, str]] = {
    "magazine": {
        "zh": "在这个信息爆炸的时代，我们每天被无数的新闻推送、社交媒体动态和短视频包围。但你有没有想过，为什么我们越来越难以静下心来阅读一篇深度长文？神经科学研究表明，长期暴露在碎片化信息中，我们的大脑正在发生微妙的变化。注意力持续时间从2000年的12秒下降到了如今的8秒，比金鱼还短。这不仅仅是一个数字的变化，它意味着我们正在丧失深度思考的能力。当我们在地铁上刷手机时，那些曾经让我们废寝忘食的长篇报道，如今却让我们感到焦虑和不耐烦。",
        "en": "In an age of information overload, we are bombarded daily with countless news alerts, social media updates, and short-form videos. But have you ever wondered why we increasingly struggle to sit down and read an in-depth article? Neuroscience research reveals that our brains are undergoing subtle changes due to prolonged exposure to fragmented information. The average attention span has dropped from twelve seconds in the year two thousand to just eight seconds today, shorter than that of a goldfish. This is not merely a statistical shift; it means we are gradually losing our capacity for deep thinking. When we scroll through our phones on the subway, those long-form reports that once captivated us for hours now trigger anxiety and impatience.",
    },
    "audiobook_biography": {
        "zh": "一九五七年的那个秋天，钱学森站在北京航空航天大学的讲台上，看着台下那些年轻的面孔。他们眼中闪烁着对知识的渴望，对未来的憧憬。他想起了自己在美国的二十年，想起了加州理工学院的实验室，想起了冯·卡门教授的谆谆教诲。但他没有后悔。当祖国需要他的时候，他毫不犹豫地选择了回来。那一刻，他知道自己正在做一件改变中国航天历史的事情。多年后，当中国的导弹划破长空，当卫星环绕地球飞行，他常常想起那个秋天的下午，想起那些年轻的面孔。",
        "en": "In the autumn of nineteen fifty-seven, Qian Xuesen stood at the podium of Beijing University of Aeronautics and Astronautics, gazing at the young faces before him. Their eyes sparkled with a thirst for knowledge and visions of the future. He thought of his twenty years in America, of the laboratories at Caltech, of Professor Theodor Von Karman's patient guidance. Yet he harbored no regrets. When his motherland needed him, he chose to return without hesitation. In that moment, he knew he was doing something that would alter the course of Chinese aerospace history. Years later, when Chinese missiles pierced the sky and satellites orbited the Earth, he would often recall that autumn afternoon and those youthful faces.",
    },
    "audiobook_nonfiction": {
        "zh": "人类的大脑重约三磅，却消耗着人体百分之二十的能量。这个看似矛盾的事实，揭示了一个深刻的进化秘密。我们的祖先在非洲大草原上生存了数百万年，为了躲避狮子、猎豹和鳄鱼的追捕，他们发展出了极其敏锐的感知系统。恐惧，这种被现代人视为负面的情绪，实际上是人类存活至今的关键。当我们感到害怕时，杏仁核会瞬间激活，肾上腺素飙升，血液从消化系统涌向四肢肌肉。这就是为什么你在过马路时差点被车撞到，会感到心跳加速、手心出汗。这不是软弱，这是你体内流淌了数百万年的生存本能。",
        "en": "The human brain weighs approximately three pounds, yet it consumes twenty percent of the body's total energy. This seemingly paradoxical fact reveals a profound evolutionary secret. Our ancestors survived on the African savanna for millions of years, and in order to evade lions, cheetahs, and crocodiles, they developed extraordinarily keen perceptual systems. Fear, an emotion that modern humans often view negatively, was actually the key to our survival. When we feel afraid, the amygdala activates instantly, adrenaline surges, and blood rushes from the digestive system to the muscles in our limbs. This is why your heart races and your palms sweat when you nearly get hit by a car while crossing the street. This is not weakness; this is the survival instinct that has coursed through your veins for millions of years.",
    },
    "audiobook_literature": {
        "zh": "孔子站在泗水之畔，看着滔滔东流的河水，陷入了沉思。子贡问道，先生为何如此凝视这流水？孔子缓缓说道，逝者如斯夫，不舍昼夜。这句话不仅仅是对时间流逝的感叹，更蕴含着深刻的人生哲学。水，看似柔弱，却能穿石而过；看似无形，却能适应万千容器。老子说上善若水，水善利万物而不争。在中国传统文化中，水被赋予了最高的道德象征。它教导我们，真正的强大不是刚硬对抗，而是像水一样，以柔克刚，以退为进。这种智慧，穿越了两千五百年的时光，至今仍然照亮着我们的生活。",
        "en": "Confucius stood at the bank of the Si River, gazing at the waters flowing eastward, lost in contemplation. Zigong asked why his teacher stared so intently at the flowing water. Confucius replied slowly, It passes just like this, ceasing not day or night. This statement is not merely a lament over the passage of time; it contains a profound philosophy of life. Water appears weak, yet it can carve through solid rock. It appears formless, yet it adapts to countless vessels. Laozi said the highest good is like water, which benefits all things without competing. In traditional Chinese culture, water has been endowed with the highest moral symbolism. It teaches us that true strength lies not in rigid confrontation, but in overcoming hardness with softness, in advancing through retreat. This wisdom has traversed twenty-five hundred years and continues to illuminate our lives today.",
    },
    "audiobook_fiction": {
        "zh": "雨下了一整夜。林小晚坐在窗前，看着雨水顺着玻璃缓缓流下，像是无数条透明的小蛇在爬行。她手里握着那封信，信纸已经被她的汗水浸湿，字迹模糊成了一片。那是他走之前留给她的，只有短短几行字：等我回来。可他已经走了三年了，三年里没有一封信，一个电话，一条消息。她不知道他去了哪里，不知道他是否还活着。但她还是每天坐在窗前，看着窗外的雨，等着那个也许永远不会回来的人。楼下的桂花开了又谢，谢了又开，她就这样一年又一年地等着。",
        "en": "The rain had been falling all night. Lin Xiaowan sat by the window, watching the raindrops slide slowly down the glass, like countless transparent serpents crawling across the surface. In her hand she held that letter, its paper already dampened by her sweat, the characters blurred into an indistinct smudge. It was what he had left for her before he departed, just a few short lines: Wait for me to return. But he had been gone for three years now, and in those three years there had been not a single letter, not one phone call, not a solitary message. She did not know where he had gone, did not know whether he was even still alive. Yet still she sat by the window every day, watching the rain outside, waiting for the person who might never come back. The osmanthus blossoms downstairs had bloomed and withered, withered and bloomed again, and so she waited, year after year.",
    },
    "audiobook_art": {
        "zh": "当你站在蒙娜丽莎面前，你看到的不仅仅是一幅画。那是达芬奇用了十六年时间，一层一层涂抹出来的神秘微笑。他用了晕涂法，让色彩在边界处自然过渡，没有明显的线条，就像真实人脸在光线下的样子。五百年来，无数人试图破解这个微笑的秘密。有人说她在笑，有人说她没有笑。有人说她是佛罗伦萨的商人妻子，有人说她是达芬奇的理想化身。但也许，这正是艺术的魅力所在。它不给你标准答案，它只是在你面前展开一个永恒的谜题，让你在凝视中不断发现新的意义。",
        "en": "When you stand before the Mona Lisa, you are looking at far more than a painting. It is that mysterious smile which Leonardo da Vinci spent sixteen years layering, brushstroke by brushstroke. He employed the technique of sfumato, allowing colors to transition naturally at their boundaries, with no harsh outlines, just as a real human face appears under light. For five hundred years, countless people have tried to decipher the secret of that smile. Some say she is laughing; others insist she is not. Some claim she was the wife of a Florentine merchant; others believe she embodies Leonardo's ideal. But perhaps this is precisely the charm of art. It offers no definitive answer. It simply unfolds an eternal enigma before your eyes, inviting you to discover new meaning in your contemplation.",
    },
    "finance": {
        "zh": "美联储今天宣布维持利率不变，这已经是连续第三次会议按兵不动。市场对此反应平淡，道琼斯指数微涨零点三个百分点。但真正的焦点在于会后声明中的微妙措辞变化。鲍威尔主席使用了'适度限制性'替代了此前的'充分限制性'，这一字之差被华尔街解读为降息窗口正在缓缓打开。债券市场迅速做出反应，十年期国债收益率下跌八个基点至百分之四点一五。分析师普遍认为，如果五月的核心PCE数据继续回落，美联储很可能在六月启动本轮周期的首次降息。",
        "en": "The Federal Reserve announced today that it will maintain interest rates unchanged, marking the third consecutive meeting where the central bank has held steady. The market's reaction was muted, with the Dow Jones Industrial Average rising a modest three tenths of a percent. However, the real focus lies in the subtle shift in wording within the post-meeting statement. Chairman Powell replaced the previous phrase 'sufficiently restrictive' with 'moderately restrictive,' a single word change that Wall Street has interpreted as the interest rate cut window slowly beginning to open. The bond market responded swiftly, with the ten-year Treasury yield falling eight basis points to four point one five percent. Analysts broadly agree that if the May core PCE data continues to decline, the Federal Reserve will very likely initiate the first rate cut of this cycle in June.",
    },
    "tech": {
        "zh": "苹果在今天凌晨的发布会上正式推出了搭载M4芯片的全新MacBook Pro。这款芯片采用了台积电最新的三纳米制程工艺，集成了二百八十亿个晶体管，比上一代M3芯片多出了百分之四十。最令人震惊的是它的神经网络引擎，每秒可执行三十八万亿次运算，这意味着本地运行大语言模型将变得轻而易举。苹果现场演示了在MacBook Pro上运行一个七十亿参数的AI模型，响应速度几乎与云端API无异。这标志着个人电脑正在从传统的计算工具，进化成为真正的AI个人助理。售价一万四千九百九十九元起，下周三正式开售。",
        "en": "At today's early morning keynote, Apple officially unveiled the all-new MacBook Pro powered by the M4 chip. This processor is built on TSMC's latest three-nanometer process technology, integrating two hundred and eighty billion transistors, a forty percent increase over the previous generation M3 chip. Most impressively, its neural engine can execute thirty-eight trillion operations per second, meaning that running large language models locally will become effortless. Apple demonstrated live a seven-billion-parameter AI model running on the MacBook Pro, with response speeds nearly indistinguishable from cloud-based APIs. This signals that personal computers are evolving from traditional computing tools into true AI personal assistants. Pricing starts at fourteen thousand nine hundred and ninety-nine yuan, with sales beginning next Wednesday.",
    },
}

OUTPUT_DIR = Path("samples")


async def generate_sample(
    client: AsyncOpenAI,
    category: str,
    lang: str,
    voice_name: str,
    voice_desc: str,
) -> bool:
    """生成单个音色 sample。"""
    out_path = OUTPUT_DIR / f"{category}_{lang}_{voice_name}.wav"
    if out_path.exists():
        print(f"  跳过（已存在）: {out_path.name}")
        return True

    text = TEST_TEXTS[category][lang]

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "user", "content": voice_desc},
                {"role": "assistant", "content": text},
            ],
            audio={"format": "wav"},
        )
        message = response.choices[0].message
        if message.audio and message.audio.data:
            audio_data = base64.b64decode(message.audio.data)
            out_path.write_bytes(audio_data)
            print(f"  ✅ {out_path.name} ({len(audio_data)} bytes)")
            return True
        print(f"  ❌ {out_path.name}: 返回空音频")
        return False
    except Exception as e:
        print(f"  ❌ {out_path.name}: {type(e).__name__}: {e}")
        return False


async def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)

    print(f"模型: {MODEL}")
    print(f"输出目录: {OUTPUT_DIR}")
    print()

    total = 0
    success = 0

    for category, lang_voices in VOICE_PROFILES.items():
        label = CATEGORY_LABELS.get(category, category)
        print(f"【{label}】")

        for lang, voices in lang_voices.items():
            for voice_name, voice_desc in voices.items():
                total += 1
                if await generate_sample(client, category, lang, voice_name, voice_desc):
                    success += 1

        print()

    print(f"完成: {success}/{total} 个 sample 已生成到 {OUTPUT_DIR}/")
    return 0 if success == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
