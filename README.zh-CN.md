🌍 [English](README.md) | [简体中文](README.zh-CN.md)

>
> 首先感谢 [Xiaomi MiMo](https://www.xiaomimimo.com/) Orbit 「百万亿 Token 创造者激励计划」赠送的一个月 Token Pro 套餐。本项目使用的 MiMo-V2.5-TTS 模型目前处于**限时免费调用**阶段，虽然生成效果并非业界最顶尖，但量大管饱、非常慷慨。
>
> 我在使用过程中发现，长文本朗读时模型的语音一致性会随上下文长度衰减（中后段语速变快、咬字模糊），因此在工程上做了大量优化（动态分块、风格保鲜、并发控制等），最终效果令人满意。开源出来分享给有需要的人 —— 我的初衷很简单：**老年人长时间看手机眼睛不舒服，初衷是给爸爸妈妈制作的有声书生成器，可以在休息和运动的时候听听有声书和杂志**。实测生成效率约为 **1:60**（1 秒处理时间生成 1 分钟音频），完全可以接受。
>
> 这个项目的基础框架是我用 MiMo-V2.5-Pro 花了半天时间手搓出来的，后续的优化和升级全程靠 **Kimi 2.6 for Coding** 的 vibe coding 能力完成。我不是专业开发者，只是五一假期在家玩票。不得不说，小米一个月 7 亿 Token 的额度虽然听起来很多，实际跑起来完全不够用 —— 这才 3 天就已经烧了 40%（当然还有别的项目和工作在跑），希望小米未来真的考虑一下用量扩容的事儿。

# Auto-Audiobook

自动化有声书生成引擎 —— 将 EPUB / MOBI / PDF 一键转化为结构化 MP3。

基于 MiMo-V2.5 TTS 与 LLM，支持并发合成、断点续传、音色选择、试听预览。零人工干预，异步高并发。

---

## 功能特性

| 特性 | 说明 |
|------|------|
| **格式支持** | EPUB / MOBI / PDF |
| **TTS 引擎** | MiMo-V2.5-TTS（OpenAI 兼容 API） |
| **并发合成** | 默认 24 并发，支持断点续传 |
| **音色选择** | 中文（茉莉、白桦、苏打、冰糖），英文（Mia、Milo、Chloe、Dean） |
| **朗读风格** | 默认 / 新闻 / 故事 / 传记 / 知识，通过 style prompt 控制语速与语气 |
| **试听预览** | 处理前先合成一段试听，满意后再全量处理 |
| **增量处理** | 自动跳过已完成的章节，支持断点续传 |
| **TTS 缓存** | 自动缓存合成结果，重复内容零 API 调用 |
| **音频输出** | 256kbps 单声道 MP3，带 ID3 标签（书名、作者、章节标题） |
| **目录监听** | Watchdog 模式，放入文件即自动处理 |

---

## 快速开始

### 1. 安装依赖

```bash
# 克隆项目
git clone <repo-url>
cd auto_audiobook

# 安装依赖（推荐 uv）
uv pip install -e .

# 或传统方式
pip install -e .
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
XIAOMI_MIMO_API_KEY=your_api_key_here
```

> **获取 API Key**: 请前往 [MiMo 开放平台控制台](https://platform.xiaomimimo.com/) 申请并获取您的 API Key。
>
> **重要说明**：
> - 目前**普通调用的 API Key** 和 **Coding Plan 的 Key** 均可使用当前的 TTS 模型。
> - **注意错配**：两者分别对应不同的 `BASE_URL`，配置时请务必自行甄别，不要填错。
> - **费用参考**：该模型目前处于限时免费阶段。实测 2 天内处理大量书籍（消耗近 200 万 Token），费用为零。

![Token Usage](docs/assets/token_usage.png)

> 如需代理：
> ```bash
> export https_proxy=http://127.0.0.1:7897
> export http_proxy=http://127.0.0.1:7897
> ```

### 3. 放入书籍

将 EPUB / MOBI / PDF 文件放入 `input/` 目录。

### 4. 运行

**交互模式（推荐）**：

```bash
python main.py
```

流程：选择文件 → 确认语言 → 选择音色（男/女）→ 选择风格 → 试听预览 → 开始处理。

**CLI 模式**：

```bash
# 单本处理
python main.py --file input/book.epub

# 批量处理目录
python main.py --input-dir input/

# 使用 LLM 清洗（默认规则引擎）
python main.py --file input/book.epub --clean-mode llm
```

**Watchdog 监听模式**：

```bash
python main.py
# 选择「监听目录」
```

---

## 最佳实践

### 1. 文本分块：600 字是甜点

MiMo TTS 的 style prompt（如 "语速偏慢、吐字清晰"）在长文本中会衰减。我们的经验：

| 分块大小 | 效果 | 建议 |
|----------|------|------|
| 3000 字 | 中后段 style 失效，囫囵吞字 | 不推荐 |
| 1500 字 | 仍有波动，偶发语速加快 | 不推荐 |
| **600 字** | **style 始终有效，音质稳定** | **推荐** |

本项目采用 **600 字软限制 + 900 字硬限制** 的动态分块策略：
- 优先在段落边界切分
- 其次在句子边界切分
- 宁可 chunk 稍长（600 ~ 900 字），也**禁止在句子中间切断**
- 极端无标点文本（如代码）才会硬切在 900 字

### 2. 并发控制：24 是上限

MiMo TTS 官方限流：**RPM 100**（每分钟 100 请求）。

| 并发数 | 表现 | 建议 |
|--------|------|------|
| 50 | 失败率 17%，大量空音频 | 过高 |
| 27 | 偶发 attempt 1 失败，需重试 | 临界 |
| **24** | **稳定，极少触发限流** | **推荐** |
| 20 | 更保守，速度慢约 10% | 安全 |

> 失败表现为 "TTS 返回空音频"，系统会自动重试（最多 3 次），但会拖慢整体速度。

### 3. 先试听，再批量

不同音色和风格差异很大。处理前先试听（交互模式自动触发）：
- 取第一章前 2 个 chunks 合成临时 MP3
- 播放试听
- 不满意可切换音色/风格后重试
- **避免批量处理后才发现效果不佳，浪费 API 调用**

### 4. 缓存自动失效机制

TTS 缓存键包含：`模型 + 音色 + 风格 + 文本`。这意味着：
- 切换音色 → 缓存自动失效（不会读到旧音频）
- 切换风格 → 缓存自动失效
- 分块算法变更 → 缓存自动失效

首次使用新配置时 0% 缓存命中属正常现象。

### 5. 断点续传与增量处理

输出目录中已存在有效 MP3 的章节会自动跳过：
- 适合长书分多次处理
- 适合网络不稳定时中断后恢复
- 注意：已有 MP3 会通过 mutagen 校验时长，损坏文件会自动重制

### 6. EPUB 章节顺序

本项目按 EPUB **spine** (书籍骨架) 顺序读取章节（而非 manifest 的物理文件顺序），确保阅读顺序正确。

---

## 架构

```
input/  ──→  parser.py  ──→  cleaner.py  ──→  synthesizer.py  ──→  assembler.py  ──→  output/
              (EPUB/PDF)      (文本清洗)        (TTS 合成)          (音频拼接)
                                ↓
                         rule_cleaner.py
                         (零 API 调用)
```

| 文件 | 职责 |
|------|------|
| `main.py` | CLI 入口、交互式界面、Watchdog 监听 |
| `config.py` | 配置管理（路径、API、音频参数、音色库） |
| `parser.py` | EPUB / MOBI / PDF 解析、文本分块 |
| `cleaner.py` | LLM 智能清洗（MiMo-V2.5-Pro） |
| `rule_cleaner.py` | 规则引擎清洗（零 API 调用，默认） |
| `synthesizer.py` | MiMo TTS 并发合成、缓存、进度条 |
| `assembler.py` | WAV 拼接、MP3 导出、ID3 标签 |
| `pipeline.py` | 主流水线编排、增量恢复、总结面板 |
| `text_processor.py` | 数字转中文读法、标点规范化 |
| `models.py` | 核心数据模型（避免循环导入） |
| `voice_profiles.py` | 音色库与场景描述 |

---

## 配置参考

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `XIAOMI_MIMO_API_KEY` | MiMo API Key | （必填） |
| `XIAOMI_MIMO_BASE_URL` | API 基础地址 | `https://api.xiaomimimo.com/v1` |
| `TTS_CONCURRENCY` | TTS 并发数 | `24` |
| `LLM_CONCURRENCY` | LLM 清洗并发数 | `5` |

### 运行时配置（config.py）

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `CHUNK_MAX_CHARS` | 分块软限制 | `600` |
| `CHUNK_HARD_LIMIT` | 分块硬上限 | `900` |
| `TTS_STYLE` | 朗读风格 | `default` |
| `CLEAN_MODE` | 清洗模式 | `rule`（可选 `llm`） |
| `MP3_BITRATE` | 输出码率 | `256k` |
| `CHAPTER_SILENCE_MS` | 章节间静音 | `1500` |

---

## 性能数据

实测环境：MacBook Air M2，Clash Verge 代理，MiMo-V2.5-TTS。

| 书籍 | 字数 | chunk 数 | 处理时间 | 音频时长 | RTF |
|------|------|----------|----------|----------|-----|
| 我在北京送快递 | 12.9 万 | 234 | 8 分 | 8:15:20 | 0.016 |
| 世上为什么要有图书馆 | ~15 万 | ~300 | 15.3 分 | ~10 小时 | ~0.025 |
| 筚路维艰 | ~18 万 | 372 | 14.1 分 | ~11 小时 | ~0.021 |

> RTF（实时因子）= 处理时间 / 音频时长。值越小越快。本项目在 24 并发下约 **40 ~ 60 倍实时**。

---

## 常见问题

**Q: 为什么有些 chunk 会出现 "TTS 返回空音频"？**

A: 这是 MiMo TTS 的 RPM 限流（100 请求 / 分钟）导致的。系统会自动重试，通常 attempt (尝试) 2 或 3 会成功。如果频繁出现，可将 `TTS_CONCURRENCY` 降到 20。

**Q: 可以换其他 TTS 引擎吗？**

A: 当前深度绑定 MiMo 的 OpenAI 兼容 API。如需接入其他引擎（如 Azure TTS、Edge TTS），需修改 `synthesizer.py` 中的 `_synthesize_single` 函数。

**Q: 支持哪些语言？**

A: 当前主要优化中文和英文。自动语言检测基于文本采样，中文书用中文音色，英文书用英文音色。

**Q: 生成的有声书可以上传到播客平台吗？**

A: **不建议**。这些是商业出版物的完整朗读，上传到公开平台（喜马拉雅、B 站、小红书）涉及版权侵权。个人收听、私人云盘备份、合理引用片段（如书评视频）是安全的。

**Q: 为什么 EPUB 解析后章节顺序不对？**

A: 早期版本按 manifest 读取，可能无序。当前版本已改为按 **spine** (骨架) 顺序读取，如果仍有问题请提 Issue。

---

## 技术文档

有关音色设计、VoiceDesign 模型集成及语言检测的深度细节，请参考：
- [VoiceDesign 音色集成设计文档](docs/superpowers/specs/2026-05-03-voice-design-integration.md)

---

## 版权与许可

本项目采用 [MIT License](LICENSE)。

**使用本项目生成的音频，请遵守以下原则：**
- 仅用于个人学习、研究、收听
- 不得将完整有声书上传至公开平台
- 尊重原作者版权，支持正版书籍

---

## 致谢

- [MiMo](https://www.xiaomimimo.com/) 提供 TTS 与 LLM API
  - [MiMo TTS v2.5 发布说明](https://platform.xiaomimimo.com/docs/zh-CN/news/v2.5-tts-release)
  - [语音合成使用指南](https://platform.xiaomimimo.com/docs/zh-CN/usage-guide/speech-synthesis-v2.5)
  - [计费与价格说明](https://platform.xiaomimimo.com/docs/zh-CN/pricing)
- [OpenAI Python SDK](https://github.com/openai/openai-python) 提供异步客户端
- [pydub](https://github.com/jiaaro/pydub) 与 [mutagen](https://mutagen.readthedocs.io/) 处理音频
