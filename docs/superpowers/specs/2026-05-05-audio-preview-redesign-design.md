# 试听对比室（Voice Lab）改造设计

**Date**: 2026-05-05
**Status**: Pending review
**Owner**: Haining

## 背景与问题

当前 `main.py:_preview_sample`（484-537 行）在交互流程"选音色 → 选风格 → 试听"的最后一步合成单个试听片段，存在两个核心问题：

1. **试听文本来自 `book.chapters[0]` 前 2 个 chunks** —— EPUB/PDF 的第一章往往是版权页、扉页、目录、前言、致谢，朗读这些内容听不出风格效果。
2. **每次只生成一个版本** —— 用户无法横向比较不同音色 / 风格，要换组合只能退回前两步重新走一次流程。

值得参考的是 `_confirm_language`（302-335 行）做语言检测时已经实现了"过滤目录章节 + 随机采样"逻辑，可直接复用。

## 目标

- 试听片段来自书籍的"真正正文"，体现真实朗读效果
- 用户可在一次会话内对比任意多个 (音色, 风格) 组合
- 改造对主流程入侵小,失败回退路径清晰
- 保留现有 chunk 级 TTS 缓存机制（`output/.tts_cache/`）

## 非目标

- 不做持久化的"试听历史"记忆
- 不做 Web UI / TUI 框架升级
- 不改动 `voice_preview.py` 独立 CLI 脚本
- 不动 parser / cleaner / synthesizer / assembler 业务模块

## 用户决策摘要

| 维度 | 决策 |
|---|---|
| 文本采样位置 | 智能跳过 + 随机抽样（复用 `_confirm_language` 过滤逻辑） |
| 对比维度 | 笛卡尔积，但用户点菜式勾选要哪几个组合 |
| 试听片段长度 | ±200 字 / 25-35 秒 |
| 听后选择 | 用户自由选听任意编号，可临时设候选，最终再确认 |
| 实现方案 | 抽出独立模块 `voice_lab.py`，main.py 仅调用 |

## 架构

### 新文件 `voice_lab.py`

唯一对外入口 `run_voice_lab(file_path, language) -> tuple[str, str]`，返回最终选定的 `(voice, style)`。内部分四个函数：

| 函数 | 职责 |
|---|---|
| `_sample_preview_text(book, target_chars=200)` | 从 `Book` 智能抽试听文本 |
| `_select_combos(language)` | `questionary.checkbox` 让用户勾选 (voice, style) 组合 |
| `_synthesize_previews(text, language, combos)` | 并发合成所有组合 → `list[PreviewItem]` |
| `_interactive_compare(items)` | 菜单循环：选听 / 标记候选 / 确认 |

### `main.py` 改动

替换 `interactive_mode` 中"选音色 / 选风格 / 旧 `_preview_sample`"三步（580-606 行）为单次 `voice_lab.run_voice_lab(...)` 调用。

删除 `_preview_sample`、`_select_voice`、`_select_style` 三个函数（功能被 voice_lab 接管）。

### 数据流

```
selected file
  ↓ parser.parse_file
Book
  ↓ _sample_preview_text  (复用 _confirm_language 的过滤逻辑)
preview_text: str (~200 字)
  ↓ _select_combos
combos: list[(voice, style)]
  ↓ _synthesize_previews  (rule_clean → synthesize → assemble → tmp .mp3)
items: list[PreviewItem]
  ↓ _interactive_compare  (菜单循环)
(voice, style)
  ↓ main.py 写回 config 进入 batch_process
```

### `PreviewItem` 数据结构

```python
@dataclass
class PreviewItem:
    voice: str
    style: str           # 'default' | 'news' | 'story' | ...
    style_label: str     # '默认（平静温暖）'
    mp3_path: Path | None  # 合成成功才有
    error: str | None    # 失败时的错误简述
    duration_sec: float  # 合成完后写入,用于显示
```

## 试听文本采样

### 算法

```python
def _sample_preview_text(book: Book, target_chars: int = 200) -> str:
    content_chapters = [
        ch for ch in book.chapters
        if len(ch.title) > 2 and sum(len(c) for c in ch.chunks) > 200
    ]
    if not content_chapters:
        content_chapters = book.chapters

    # 最多重抽 3 次（防 chunks 为空）
    for _ in range(3):
        chapter = random.choice(content_chapters)
        if chapter.chunks:
            break
    else:
        return ""

    text = _truncate_at_sentence(chapter.chunks[0], target_chars)

    # 不足 50 字则拼接同章节后续 chunks（不修改原 Book 对象）
    idx = 1
    while len(text) < 50 and idx < len(chapter.chunks):
        text += chapter.chunks[idx][: target_chars - len(text)]
        idx += 1
    return text
```

### 自然边界截断

```python
_SENTENCE_END = re.compile(r'[。！？!?\.](?=[^"」』])')

def _truncate_at_sentence(text: str, target: int) -> str:
    if len(text) <= target:
        return text
    window = text[: int(target * 1.3)]
    cuts = [m.end() for m in _SENTENCE_END.finditer(window)]
    cuts = [c for c in cuts if c >= target * 0.7]
    if cuts:
        return text[: cuts[0]]
    return text[:target]
```

在 `[target*0.7, target*1.3]` 区间内找最近的句末标点，避免半句被切断。无句号则硬截断兜底。

### 单点采样原则

`run_voice_lab` 调用一次 `_sample_preview_text` 后将结果作为局部变量复用 —— **所有勾选的组合都用这同一段文本**，确保 A/B 比较中"音色差"不被"文本差"污染。

## 试听对比室交互

### 菜单 UI（rich.Table + questionary.select）

```
╭─ 试听对比室 ──────────────────────────────────────╮
│  #  音色      风格        状态        候选       │
│  1  茉莉      默认        ✓ 已生成    ★          │
│  2  茉莉      故事        ✓ 已生成              │
│  3  白桦      默认        ✓ 已生成              │
│  4  苏打      新闻        ✗ 合成失败            │
╰────────────────────────────────────────────────────╯
当前候选：#1 茉莉 × 默认

? 下一步操作：
> ▶ 试听 #N
  ★ 设 #N 为候选
  ↻ 全部重新生成（换一段试听文本）
  + 添加更多组合
  ✓ 确认当前候选并继续
  ✗ 取消（用默认音色/风格）
```

### 交互细节

| 行为 | 实现 |
|---|---|
| 默认勾选 | 当前语言下所有音色 × `default` 风格（4 个） |
| 默认候选 | 第一个合成成功的项自动设为候选 |
| 试听 #N | 输入编号 → 跨平台播放 → 播完回菜单 |
| 设 #N 为候选 | 输入编号 → 标记移到该行 → 重绘表格 |
| 重生成 | 重抽文本 + 重选组合 + 重合成；旧 mp3 立即 unlink |
| 添加组合 | 增量合成，已有项不重复 |
| 失败项 | 状态列 `✗`，禁止试听/设候选 |
| 退出 / Ctrl+C | 回退到 `config.TTS_VOICES[language]` + `'default'` |

### 上限保护

`_select_combos` 在勾选 > 20 个时弹 `confirm("勾选 N 个，预计 ~M 秒，确认？")`，软提示不强阻断。

## 错误处理与回退

### 临时文件管理

```python
async def run_voice_lab(file_path, language) -> tuple[str, str]:
    tmp_dir = Path(tempfile.mkdtemp(prefix="voice_lab_"))
    try:
        ...
        return await _interactive_compare(items)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

`finally` 保证试听 mp3 在所有退出路径（含 Ctrl+C、异常、正常返回）下被清理。

### 错误矩阵

| 失败点 | 行为 | 用户提示 |
|---|---|---|
| `parse_file` 抛异常 | 警告 + 返回默认 | "试听准备失败，使用默认配置继续" |
| 单个 TTS 调用失败 | 标 `error`，其他继续 | 表格该行 `✗ 简述` |
| 所有 TTS 调用失败 | 警告 + 返回默认 | "全部试听合成失败，使用默认配置继续" |
| Ctrl+C | finally 清理 → 抛出，由 main.py 捕获 | 回主菜单 |
| 播放器缺失 | 警告日志 + 给出 mp3 路径 | "无法播放，文件位于: ..." |

### 与现有缓存的关系

不引入新缓存。现有 `output/.tts_cache/` 按 `sha256(text + voice + style)` 命名 chunk 级缓存，试听走同一 `synthesize_chapters`，命中机制自动生效 —— 同一段文本 + 同一组合二次合成 0 调用 API。

## 测试

项目当前无 `tests/` 目录，本次新建并初始化为 pytest 项目（`tests/__init__.py`、`tests/conftest.py` 留空即可，依赖已在 venv 中）。新建 `tests/test_voice_lab.py`：

| 测试用例 | 类型 |
|---|---|
| `test_sample_preview_text_filters_toc` | 单测：构造 5 章假 Book（前 2 章标题短/内容少），验证抽中的非前两个 |
| `test_truncate_at_sentence_finds_natural_boundary` | 单测：纯函数 |
| `test_truncate_at_sentence_fallback_hard_cut` | 单测：无句号文本兜底 |
| `test_sample_preview_text_fallback_when_all_filtered` | 单测：所有章节都被过滤时回退到原始章节 |
| `test_synthesize_previews_partial_failure` | 集成：mock 一个 TTS 失败，验证其他项不受影响 |
| `test_select_combos_default_includes_default_style` | 单测：mock questionary，验证默认勾选 |

`_interactive_compare` 菜单循环不写自动化测试（手测验证）。

## 验收标准

1. EPUB / PDF 输入：试听文本不再来自版权页 / 目录页（5 本不同来源书籍人工抽查）
2. 同一会话内可生成 ≥ 2 个组合并自由切换试听
3. 任意组合合成失败不影响其他组合 / 不阻塞主流程
4. 退出试听对比室后能进入正常的 `batch_process`
5. `tests/test_voice_lab.py` 全部通过

## 文件清单

| 文件 | 改动 |
|---|---|
| `voice_lab.py` | 新建（~200 行） |
| `main.py` | 删除 `_preview_sample` / `_select_voice` / `_select_style`，替换 `interactive_mode` 中相应步骤（~30 行净减少） |
| `tests/__init__.py` | 新建（空文件） |
| `tests/test_voice_lab.py` | 新建（~100 行） |
| `voice_preview.py` | **不动** |
| `parser.py` / `cleaner.py` / `synthesizer.py` / `assembler.py` / `pipeline.py` | **不动** |
| `config.py` | **不动**（依赖现有 `TTS_VOICE_OPTIONS` / `TTS_STYLE_PRESETS`） |
