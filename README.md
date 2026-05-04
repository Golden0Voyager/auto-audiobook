🌍 [English](README.md) | [简体中文](README.zh-CN.md)

>
> Special thanks to [Xiaomi MiMo](https://www.xiaomimimo.com/) Orbit "Trillion Token Creator Incentive Program" for providing a one-month Token Pro package. The MiMo-V2.5-TTS model used in this project is currently in the **limited-time free trial** stage. While the generation quality might not be the absolute top in the industry, it is generous and highly efficient for batch processing.
>
> During usage, I noticed that for long-text reading, the model's voice consistency tends to degrade as the context length increases (speeding up or becoming blurred in the middle and later stages). Therefore, I have implemented significant optimizations (dynamic chunking, style preservation, concurrency control, etc.), leading to satisfying results. I'm open-sourcing this for anyone in need—my original motivation was simple: **My parents find it uncomfortable to stare at mobile screens for long periods, so I built this generator to create audiobooks for them to enjoy while resting or exercising.** The actual generation efficiency is approximately **1:60** (1 second of processing for 1 minute of audio), which is quite acceptable.
>
> The base framework of this project was manually prototyped by me using MiMo-V2.5-Pro in half a day, and subsequent optimizations were entirely completed through the **vibe coding** capabilities of **Kimi 2.6 for Coding**. I am not a professional developer; I just tinkered with this during the May Day holiday. I must say, although Xiaomi's 700 million token monthly quota sounds like a lot, it burns through surprisingly fast—40% was consumed in just 3 days (with other projects running). I hope Xiaomi considers expanding the quota in the future.

# Auto-Audiobook

Automated audiobook generation engine —— Converting EPUB / MOBI / PDF to structured MP3 with one click.

Based on MiMo-V2.5 TTS and LLM, supporting concurrent synthesis, breakpoint resume, voice selection, and preview. Zero manual intervention, asynchronous high concurrency.

---

## Features

| Feature | Description |
|------|------|
| **Format Support** | EPUB / MOBI / PDF |
| **TTS Engine** | MiMo-V2.5-TTS (OpenAI-compatible API) |
| **Concurrent Synthesis** | Default 24 threads, supports breakpoint resume |
| **Voice Selection** | Chinese (Molly, Birch, Soda, RockSugar), English (Mia, Milo, Chloe, Dean) |
| **Reading Style** | Default / News / Story / Biography / Knowledge, controlled by style prompts |
| **Preview** | Synthesize a trial snippet before full processing |
| **Incremental Processing** | Automatically skip completed chapters, support for resuming |
| **TTS Cache** | Result caching for zero-cost repeated content synthesis |
| **Audio Output** | 256kbps mono MP3 with ID3 tags (Title, Author, Chapter) |
| **Directory Monitoring** | Watchdog mode for automated processing of new files |

---

## Quick Start

### 1. Install Dependencies

```bash
# Clone the repo
git clone <repo-url>
cd auto_audiobook

# Install dependencies (uv recommended)
uv pip install -e .

# Or traditional pip
pip install -e .
```

### 2. Configure Environment Variables

Create a `.env` file:

```bash
XIAOMI_MIMO_API_KEY=your_api_key_here
```

> **Get API Key**: Please go to the [MiMo Platform Console](https://platform.xiaomimimo.com/) to apply for and obtain your API Key.
>
> **Important Note**:
> - Both **Standard API Keys** and **Coding Plan Keys** can access the current TTS model.
> - **Avoid Mismatch**: They correspond to different `BASE_URL` values. Please ensure you use the correct URL for your key type to avoid configuration errors.
> - **Cost Reference**: The model is currently in a limited-time free trial. Real-world testing showed nearly 2 million tokens consumed in 2 days with zero cost.

![Token Usage](docs/assets/token_usage.png)

> If proxy is needed:
> ```bash
> export https_proxy=http://127.0.0.1:7897
> export http_proxy=http://127.0.0.1:7897
> ```

### 3. Add Books

Place EPUB / MOBI / PDF files into the `input/` directory.

### 4. Run

**Interactive Mode (Recommended)**:

```bash
python main.py
```

Process: Select file → Confirm language → Select voice (Male/Female) → Select style → Preview snippet → Start processing.

**CLI Mode**:

```bash
# Single file processing
python main.py --file input/book.epub

# Batch processing a directory
python main.py --input-dir input/

# Use LLM for cleaning (Default: rule-based engine)
python main.py --file input/book.epub --clean-mode llm
```

**Watchdog Monitoring Mode**:

```bash
python main.py
# Select "Monitor Directory"
```

---

## Best Practices

### 1. Text Chunking: 600 characters is the sweet spot

The style prompts of MiMo TTS (e.g., "slow speed, clear articulation") tend to decay in long texts. Our experience:

| Chunk Size | Performance | Recommendation |
|----------|------|------|
| 3000 chars | Style fails in the later stage, blurred pronunciation | Not recommended |
| 1500 chars | Still some fluctuations, occasional speed-up | Not recommended |
| **600 chars** | **Style remains effective, stable quality** | **Recommended** |

This project adopts a **600-char soft limit + 900-char hard limit** dynamic chunking strategy:
- Prioritize splitting at paragraph boundaries.
- Secondarily at sentence boundaries.
- Prefer slightly longer chunks (600~900 chars) over cutting in the middle of a sentence.
- Hard cuts at 900 chars are only used for text without punctuation (e.g., code).

### 2. Concurrency Control: 24 is the upper limit

MiMo TTS official rate limit: **RPM 100** (100 requests per minute).

| Concurrency | Behavior | Recommendation |
|--------|------|------|
| 50 | 17% failure rate, lots of empty audio | Too high |
| 27 | Occasional attempt 1 failure, requires retry | Critical |
| **24** | **Stable, rarely triggers rate limiting** | **Recommended** |
| 20 | More conservative, ~10% slower | Safe |

> Failures manifest as "TTS returned empty audio". The system will automatically retry up to 3 times, but it slows down the overall speed.

### 3. Preview first, then batch

Voices and styles vary significantly. Preview before full processing (automatically triggered in interactive mode):
- Synthesize the first 2 chunks of the first chapter into a temporary MP3.
- Play and listen.
- If unsatisfied, switch voice/style and try again.
- **Avoid batch processing only to find the results unsatisfactory, wasting API tokens.**

### 4. Automatic Cache Invalidation

TTS cache keys include: `Model + Voice + Style + Text`. This means:
- Switching Voice → Cache invalidates automatically.
- Switching Style → Cache invalidates automatically.
- Changing Chunking Algorithm → Cache invalidates automatically.

### 5. Breakpoint Resumption and Incremental Processing

Chapters with valid MP3s already in the output directory will be automatically skipped:
- Suitable for processing long books across multiple sessions.
- Suitable for recovery after network interruptions.
- Note: Existing MP3s are verified for duration via mutagen; corrupted files are remade.

### 6. EPUB Chapter Order

This project reads chapters according to the EPUB **spine** order (rather than the physical file order in manifest), ensuring correct reading sequence.

---

## Architecture

```
input/  ──→  parser.py  ──→  cleaner.py  ──→  synthesizer.py  ──→  assembler.py  ──→  output/
              (EPUB/PDF)      (Text Cleaning)   (TTS Synthesis)    (Audio Merging)
                                ↓
                         rule_cleaner.py
                         (Zero API Cost)
```

| File | Responsibility |
|------|------|
| `main.py` | CLI Entry, Interactive Interface, Watchdog Monitoring |
| `config.py` | Configuration (Paths, API, Audio params, Voice profiles) |
| `parser.py` | EPUB / MOBI / PDF parsing, text chunking |
| `cleaner.py` | LLM-based intelligent cleaning (MiMo-V2.5-Pro) |
| `rule_cleaner.py` | Rule-based cleaning (Zero API cost, default) |
| `synthesizer.py` | Concurrent synthesis, caching, progress tracking |
| `assembler.py` | WAV merging, MP3 export, ID3 tagging |
| `pipeline.py` | Pipeline orchestration, incremental recovery, summary dashboard |
| `text_processor.py` | Number-to-Chinese conversion, punctuation normalization |
| `models.py` | Core data models (avoiding circular imports) |
| `voice_profiles.py` | Voice profiles and scenario descriptions |

---

## Configuration Reference

### Environment Variables

| Variable | Description | Default Value |
|------|------|--------|
| `XIAOMI_MIMO_API_KEY` | MiMo API Key | (Required) |
| `XIAOMI_MIMO_BASE_URL` | API Base URL | `https://api.xiaomimimo.com/v1` |
| `TTS_CONCURRENCY` | TTS concurrency threads | `24` |
| `LLM_CONCURRENCY` | LLM cleaning concurrency | `5` |

### Runtime Configuration (config.py)

| Parameter | Description | Default Value |
|------|------|--------|
| `CHUNK_MAX_CHARS` | Soft limit for chunking | `600` |
| `CHUNK_HARD_LIMIT` | Hard limit for chunking | `900` |
| `TTS_STYLE` | Reading style | `default` |
| `CLEAN_MODE` | Cleaning mode | `rule` (or `llm`) |
| `MP3_BITRATE` | Output bitrate | `256k` |
| `CHAPTER_SILENCE_MS` | Silence between chapters | `1500` |

---

## Performance Data

Test environment: MacBook Air M2, Clash Verge proxy, MiMo-V2.5-TTS.

| Book | Chars | Chunks | Process Time | Audio Duration | RTF |
|------|------|----------|----------|----------|-----|
| 我在北京送快递 | 129k | 234 | 8 min | 8:15:20 | 0.016 |
| 世上为什么要有图书馆 | ~150k | ~300 | 15.3 min | ~10 hours | ~0.025 |
| 筚路维艰 | ~180k | 372 | 14.1 min | ~11 hours | ~0.021 |

> RTF (Real-Time Factor) = Process Time / Audio Duration. Smaller is faster. This project achieves approximately **40~60x real-time speed** at 24 concurrency.

---

## FAQ

**Q: Why do some chunks return "TTS returned empty audio"?**

A: This is caused by MiMo TTS RPM limit (100 RPM). The system will automatically retry, and attempt 2 or 3 usually succeeds. If it occurs frequently, lower `TTS_CONCURRENCY` to 20.

**Q: Can I use other TTS engines?**

A: Currently, it is deeply integrated with MiMo's OpenAI-compatible API. To integrate others (e.g., Azure TTS, Edge TTS), modify the `_synthesize_single` function in `synthesizer.py`.

**Q: Which languages are supported?**

A: Currently optimized for Chinese and English. Automatic language detection is based on text sampling.

**Q: Can generated audiobooks be uploaded to podcast platforms?**

A: **Not recommended**. These are full readings of commercial publications. Uploading to public platforms (Himalaya, Bilibili, Red, etc.) may involve copyright infringement. Personal listening, private cloud backup, or fair use of snippets are safe.

**Q: Why is the chapter order wrong after EPUB parsing?**

A: Early versions read via manifest, which might be unordered. The current version reads via the **spine**, which should ensure correct sequence.

---

## Technical Documentation

For in-depth details on voice design, VoiceDesign model integration, and language detection, please refer to:
- [VoiceDesign Integration Specification](docs/superpowers/specs/2026-05-03-voice-design-integration.md)

---

## License & Copyright

This project is licensed under the [MIT License](LICENSE).

**When using audio generated by this project, please adhere to the following:**
- Use for personal learning, research, and listening only.
- Do not upload full audiobooks to public platforms.
- Respect original authors' copyright and support legal copies.

---

## Acknowledgments

- [MiMo](https://www.xiaomimimo.com/) for providing TTS and LLM APIs
  - [MiMo TTS v2.5 Release Notes](https://platform.xiaomimimo.com/docs/zh-CN/news/v2.5-tts-release)
  - [Speech Synthesis Guide](https://platform.xiaomimimo.com/docs/zh-CN/usage-guide/speech-synthesis-v2.5)
  - [Pricing](https://platform.xiaomimimo.com/docs/zh-CN/pricing)
- [OpenAI Python SDK](https://github.com/openai/openai-python) for the asynchronous client
- [pydub](https://github.com/jiaaro/pydub) and [mutagen](https://mutagen.readthedocs.io/) for audio processing
