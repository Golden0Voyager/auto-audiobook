"""音频拼接 + MP3 导出 + ID3 标签注入。"""

from __future__ import annotations

import io
import re
from pathlib import Path

from mutagen.id3 import ID3, TALB, TIT2, TPE1, TRCK
from mutagen.mp3 import MP3
from pydub import AudioSegment

from config import CHAPTER_SILENCE_MS, MP3_BITRATE, MP3_CHANNELS
from models import ChapterAudio


def assemble_book(
    chapter_audios: list[ChapterAudio],
    book_title: str,
    book_author: str,
    output_dir: Path,
) -> tuple[list[Path], int]:
    """为整本书生成带标签的 MP3 文件。返回 (文件路径列表, 总时长毫秒)。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []
    total_duration_ms = 0

    for ch_audio in chapter_audios:
        if not ch_audio.audio_chunks:
            continue

        combined = _concat_wav_chunks(ch_audio.audio_chunks)
        if len(combined) == 0:
            continue

        total_duration_ms += len(combined)  # pydub AudioSegment len() 返回毫秒

        filename = _sanitize_filename(f"{ch_audio.track_num:02d}_{ch_audio.title}.mp3")
        mp3_path = output_dir / filename

        export_to_mp3(combined, mp3_path)
        write_id3_tags(mp3_path, book_title, book_author, ch_audio.title, ch_audio.track_num)
        output_paths.append(mp3_path)

    return output_paths, total_duration_ms


def _concat_wav_chunks(chunks: list[bytes]) -> AudioSegment:
    """拼接多个 WAV bytes 为单个 AudioSegment。O(n) 实现，避免 repeated + 的 O(n²) 拷贝。"""
    segments = [
        AudioSegment.from_wav(io.BytesIO(c))
        for c in chunks if c
    ]
    if not segments:
        return AudioSegment.empty()

    # 统一格式并以第一个 segment 为基准
    base = segments[0]
    silence = (
        AudioSegment.silent(duration=CHAPTER_SILENCE_MS)
        .set_frame_rate(base.frame_rate)
        .set_sample_width(base.sample_width)
        .set_channels(base.channels)
    )

    # 直接拼接底层 PCM 数据，避免 pydub 每次 + 都全量拷贝
    parts: list[bytes] = []
    for i, seg in enumerate(segments):
        seg = (
            seg.set_frame_rate(base.frame_rate)
            .set_sample_width(base.sample_width)
            .set_channels(base.channels)
        )
        if i > 0:
            parts.append(silence.raw_data)
        parts.append(seg.raw_data)

    return AudioSegment(
        data=b"".join(parts),
        sample_width=base.sample_width,
        frame_rate=base.frame_rate,
        channels=base.channels,
    )


def export_to_mp3(audio: AudioSegment, output_path: Path, bitrate: str = MP3_BITRATE) -> None:
    """导出为 MP3 格式。"""
    audio = audio.set_channels(MP3_CHANNELS)
    audio.export(str(output_path), format="mp3", bitrate=bitrate)


def write_id3_tags(
    mp3_path: Path,
    book_title: str,
    book_author: str,
    chapter_title: str,
    track_num: int,
) -> None:
    """写入 ID3 标签。"""
    try:
        audio = MP3(str(mp3_path))
        if audio.tags is None:
            audio.add_tags()
    except Exception:
        audio = MP3(str(mp3_path))
        audio.add_tags()

    tags = audio.tags
    tags.add(TIT2(encoding=3, text=[f"{book_title} — {chapter_title}"]))
    tags.add(TPE1(encoding=3, text=[book_author]))
    tags.add(TALB(encoding=3, text=[book_title]))
    tags.add(TRCK(encoding=3, text=[str(track_num)]))
    tags.save(str(mp3_path))


def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符。"""
    return re.sub(r'[<>:"/\\|?*]', "_", name)
