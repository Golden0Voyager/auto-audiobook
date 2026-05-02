"""音频拼接 + MP3 导出 + ID3 标签注入。"""

from __future__ import annotations

import io
import re
from pathlib import Path

from mutagen.id3 import ID3, TALB, TIT2, TPE1, TRCK
from mutagen.mp3 import MP3
from pydub import AudioSegment

from config import CHAPTER_SILENCE_MS, MP3_BITRATE, MP3_CHANNELS
from synthesizer import ChapterAudio


def assemble_book(
    chapter_audios: list[ChapterAudio],
    book_title: str,
    book_author: str,
    output_dir: Path,
) -> list[Path]:
    """为整本书生成带标签的 MP3 文件。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []

    for ch_audio in chapter_audios:
        if not ch_audio.audio_chunks:
            continue

        combined = _concat_wav_chunks(ch_audio.audio_chunks)
        if len(combined) == 0:
            continue

        filename = _sanitize_filename(f"{ch_audio.track_num:02d}_{ch_audio.title}.mp3")
        mp3_path = output_dir / filename

        export_to_mp3(combined, mp3_path)
        write_id3_tags(mp3_path, book_title, book_author, ch_audio.title, ch_audio.track_num)
        output_paths.append(mp3_path)

    return output_paths


def _concat_wav_chunks(chunks: list[bytes]) -> AudioSegment:
    """拼接多个 WAV bytes 为单个 AudioSegment。"""
    combined = AudioSegment.empty()
    silence = AudioSegment.silent(duration=CHAPTER_SILENCE_MS)

    for i, chunk in enumerate(chunks):
        if not chunk:
            continue
        segment = AudioSegment.from_wav(io.BytesIO(chunk))
        if i > 0:
            combined += silence
        combined += segment

    return combined


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
