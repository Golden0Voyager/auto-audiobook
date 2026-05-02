# Auto_Audiobook — 自动化有声书生成引擎

## 项目简介

基于 Python 的全自动文本转语音流水线，将 EPUB/MOBI/PDF 文档自动转化为结构化 MP3 有声书。零人工干预，异步高并发。

## 架构

| 文件 | 职责 |
|------|------|
| `config.py` | 配置管理（路径、API、音频参数） |
| `parser.py` | EPUB/MOBI/PDF 解析 + 文本分块 |
| `cleaner.py` | MiMo-V2.5-Pro LLM 智能清洗 |
| `rule_cleaner.py` | 规则引擎清洗（零 API 调用） |
| `synthesizer.py` | MiMo-V2.5-TTS 并发语音合成 |
| `assembler.py` | 音频拼接 + MP3 导出 + ID3 标签 |
| `pipeline.py` | 主流水线编排 |
| `main.py` | 入口（watchdog 监听 + CLI） |

## 技术栈

- **TTS**: MiMo-V2.5-TTS（OpenAI 兼容 API）
- **LLM**: MiMo-V2.5-Pro（文本清洗）
- **EPUB/PDF**: ebooklib + BeautifulSoup4 + pdfplumber
- **音频**: pydub + mutagen + ffmpeg
- **异步**: openai SDK (async) + asyncio
- **监听**: watchdog

## 常用命令

```bash
# 安装依赖
uv pip install -e .

# CLI 模式处理单本书（默认规则引擎清洗）
python main.py --file input/book.epub
python main.py --file input/report.pdf

# 使用 LLM 清洗模式
python main.py --file input/book.epub --clean-mode llm

# Watchdog 模式（监听 input/ 目录）
python main.py
```

## 清洗模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `rule` | 规则引擎（默认） | 小说、研报等纯文本，零成本 |
| `llm` | MiMo-V2.5-Pro LLM | 需要口语化转换的复杂文本 |

## 环境变量

- `XIAOMI_MIMO_API_KEY` — MiMo 平台 API Key

## 开发规范

- **包管理**：始终使用 `uv pip install`，不用 pip
- **语言**：始终用中文回复
- **代理**：终端需配置 `export https_proxy=http://127.0.0.1:7897`
- **音频规格**：256kbps 单声道 MP3（高音质纯人声）
- **并发控制**：Semaphore ≤ 5（平衡速度与 API 限流）

## 目录说明

```
auto_audiobook/
├── input/          # 监听文件夹（放入 EPUB/MOBI/PDF）
└── output/         # 输出目录（按书名建子目录）
```
