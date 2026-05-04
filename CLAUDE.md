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

## 性能优化

| 优化项 | 说明 |
|--------|------|
| TTS 并发 | 默认 10 并发（可通过 `TTS_CONCURRENCY` 调整） |
| 文本块大小 | 默认 3000 字符（可通过 `CHUNK_MAX_CHARS` 调整） |
| TTS 缓存 | 自动缓存合成结果到 `output/.tts_cache/` |
| 增量处理 | 自动跳过已处理的章节，支持断点续传 |

## 开发规范

- **包管理**：始终使用 `uv pip install`，不用 pip
- **语言**：始终用中文回复
- **代理**：终端需配置 `export https_proxy=http://127.0.0.1:7897`
- **音频规格**：256kbps 单声道 MP3（高音质纯人声）
- **并发控制**：TTS 默认 10 并发

## 目录说明

```
auto_audiobook/
├── input/          # 监听文件夹（放入 EPUB/MOBI/PDF）
└── output/         # 输出目录（按书名建子目录）
    └── .tts_cache/ # TTS 缓存目录
```

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%)
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->