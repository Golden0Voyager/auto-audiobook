# VoiceDesign 音色集成设计文档

## 概述

将 MiMo-V2.5-TTS VoiceDesign 模型集成到自动有声书生成引擎，支持按场景和语言选择音色。

## 设计目标

1. 支持 8 种内容场景，每种场景提供 2 个音色选项
2. 自动检测文本语言（中文/英文）
3. 提供交互式终端界面供用户选择音色
4. 保持与现有 pipeline 的兼容性

## 音色库结构

| 场景 | 中文音色 | 英文音色 |
|------|---------|---------|
| 杂志文章播报 | mature_male / warm_female | articulate_male / engaging_female |
| 有声书 - 传记 | storyteller_male / gentle_female | narrator_male / narrator_female |
| 有声书 - 非小说 | professional_male / analytical_female | informative_male / engaging_female |
| 有声书 - 文史哲 | classic_male / scholarly_female | literary_male / elegant_female |
| 有声书 - 小说 | gentle_female / storyteller_male | warm_female / dramatic_male |
| 有声书 - 艺术类 | elegant_female / cultured_male | refined_female / cultured_male |
| 财经新闻播讲 | professional_male / analytical_female | authoritative_male / insightful_female |
| 科技类内容 | young_male / calm_female | dynamic_male / clear_female |

## 文件结构

```
auto_audiobook/
├── voice_profiles.py      # 音色库定义
├── voice_selector.py      # 交互式选择器
├── text_processor.py      # 新增语言检测
├── synthesizer.py         # 集成 VoiceDesign
├── pipeline.py            # 支持音色参数
├── main.py                # CLI 参数和交互界面
└── config.py              # 模型配置
```

## 使用方式

### 交互式模式（推荐）
```bash
.venv/bin/python main.py
```

### CLI 指定音色
```bash
.venv/bin/python main.py --file input/book.epub --category magazine --voice mature_male
```

### 批量处理
```bash
.venv/bin/python main.py --input-dir input/ --category audiobook_fiction --voice storyteller_male
```

### 列出所有音色
```bash
.venv/bin/python main.py --list-voices
```

## 技术实现

### 语言检测
- 基于中文字符比例（>30% 为中文）
- 取前 500 字符进行检测
- 默认为中文

### 音色缓存
- 使用音色描述 + 处理后文本的 MD5 作为缓存键
- 缓存目录：`output/.tts_cache/`

### API 调用
- 模型：`mimo-v2.5-tts-voicedesign`
- 格式：WAV
- 并发：25（可通过 TTS_CONCURRENCY 调整）
- 文本块大小：500 字符（VoiceDesign 模型适合短文本）

## 已完成

- [x] 音色库定义（voice_profiles.py）
- [x] 交互式选择器（voice_selector.py）
- [x] 语言检测功能（text_processor.py）
- [x] VoiceDesign 模型集成（synthesizer.py）
- [x] Pipeline 参数支持（pipeline.py）
- [x] CLI 参数和交互界面（main.py）
- [x] 模型配置更新（config.py）
- [x] 集成测试通过

## 待优化

- [ ] 音色描述可进一步优化
- [ ] 可添加试听功能
- [ ] 可支持自定义音色描述
