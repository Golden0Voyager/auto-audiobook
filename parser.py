"""EPUB/MOBI/PDF 解析 + 文本分块。"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import ebooklib
import pdfplumber
from bs4 import BeautifulSoup
from ebooklib import epub

from config import CHUNK_MAX_CHARS


@dataclass
class Chapter:
    title: str
    chunks: list[str]


@dataclass
class BookData:
    title: str
    author: str
    language: str = "zh"  # "zh" or "en"
    chapters: list[Chapter] = field(default_factory=list)


def parse_epub(file_path: Path) -> BookData:
    """读取 EPUB，提取元数据和正文，按章节分块。"""
    book = epub.read_epub(str(file_path))

    title = _get_metadata(book, "title", file_path.stem)
    author = _get_metadata(book, "creator", "Unknown")

    chapters: list[Chapter] = []
    toc_titles = _extract_toc_titles(book)

    for idx, item in enumerate(book.get_items_of_type(ebooklib.ITEM_DOCUMENT)):
        html_content = item.get_content().decode("utf-8", errors="replace")
        text = _strip_html(html_content)
        if not text.strip():
            continue

        chapter_title = toc_titles[idx] if idx < len(toc_titles) else f"Chapter {idx + 1}"
        chunks = chunk_text(text, CHUNK_MAX_CHARS)
        if chunks:
            chapters.append(Chapter(title=chapter_title, chunks=chunks))

    language = detect_language(chapters)
    return BookData(title=title, author=author, language=language, chapters=chapters)


def parse_pdf(file_path: Path) -> BookData:
    """读取 PDF，提取文本并按章节分块。"""
    chapters: list[Chapter] = []
    current_title = "Chapter 1"
    current_text = ""

    with pdfplumber.open(str(file_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text:
                continue

            # 尝试检测章节标题（中文数字或阿拉伯数字开头）
            chapter_match = re.match(
                r"^(第[一二三四五六七八九十百千\d]+[章节篇]|Chapter\s+\d+|[IVX]+\.\s)",
                text.strip(),
            )
            if chapter_match and current_text.strip():
                # 保存当前章节
                chunks = chunk_text(current_text, CHUNK_MAX_CHARS)
                if chunks:
                    chapters.append(Chapter(title=current_title, chunks=chunks))
                current_title = chapter_match.group(0).strip()
                current_text = text
            else:
                current_text += "\n" + text

    # 保存最后一个章节
    if current_text.strip():
        chunks = chunk_text(current_text, CHUNK_MAX_CHARS)
        if chunks:
            chapters.append(Chapter(title=current_title, chunks=chunks))

    # 如果没有检测到章节，按页面数量分块
    if not chapters:
        all_text = ""
        with pdfplumber.open(str(file_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"
        chunks = chunk_text(all_text, CHUNK_MAX_CHARS)
        if chunks:
            chapters.append(Chapter(title="全文", chunks=chunks))

    title = file_path.stem
    author = "Unknown"
    language = detect_language(chapters)
    return BookData(title=title, author=author, language=language, chapters=chapters)


def parse_file(file_path: Path) -> BookData:
    """解析 EPUB、MOBI 或 PDF 文件。"""
    suffix = file_path.suffix.lower()
    if suffix == ".mobi":
        epub_path = convert_mobi_to_epub(file_path)
        return parse_epub(epub_path)
    if suffix == ".pdf":
        return parse_pdf(file_path)
    return parse_epub(file_path)


def convert_mobi_to_epub(mobi_path: Path) -> Path:
    """调用 calibre ebook-convert 将 MOBI 转为 EPUB。"""
    epub_path = mobi_path.with_suffix(".epub")
    if epub_path.exists():
        return epub_path

    result = subprocess.run(
        ["ebook-convert", str(mobi_path), str(epub_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"MOBI 转换失败: {result.stderr}")

    return epub_path


def chunk_text(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    """按句号/段落断句，控制单块 ≤ max_chars 字。"""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    buffer = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(buffer) + len(para) + 1 <= max_chars:
            buffer = f"{buffer}\n{para}" if buffer else para
        else:
            if buffer:
                chunks.append(buffer.strip())
            if len(para) > max_chars:
                sub_chunks = _split_long_paragraph(para, max_chars)
                chunks.extend(sub_chunks)
            else:
                buffer = para
                continue
            buffer = ""

    if buffer.strip():
        chunks.append(buffer.strip())

    return chunks


def _split_long_paragraph(text: str, max_chars: int) -> list[str]:
    """将超长段落按句子边界拆分。"""
    sentences = re.split(r"(?<=[。！？.!?])", text)
    chunks: list[str] = []
    buffer = ""

    for sent in sentences:
        if not sent.strip():
            continue
        if len(buffer) + len(sent) <= max_chars:
            buffer += sent
        else:
            if buffer:
                chunks.append(buffer.strip())
            buffer = sent

    if buffer.strip():
        chunks.append(buffer.strip())

    return chunks


def _strip_html(html: str) -> str:
    """剥离 HTML 标签，提取纯文本。"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _get_metadata(book: epub.EpubBook, key: str, default: str) -> str:
    """安全提取 EPUB 元数据。"""
    values = book.get_metadata("DC", key)
    if values:
        return values[0][0].strip()
    return default


def detect_language(chapters: list[Chapter]) -> str:
    """检测书籍语言，取前 3 章的前 3 个文本块采样。返回 "zh" 或 "en"。"""
    sample = ""
    for ch in chapters[:3]:
        for chunk in ch.chunks[:3]:
            sample += chunk
        if len(sample) >= 500:
            break

    if not sample:
        return "zh"

    # 统计中文字符占比
    chinese_chars = sum(1 for c in sample if "一" <= c <= "鿿")
    ratio = chinese_chars / len(sample) if sample else 0
    return "zh" if ratio > 0.3 else "en"


def _extract_toc_titles(book: epub.EpubBook) -> list[str]:
    """从 TOC 提取章节标题列表。"""
    titles: list[str] = []

    def _walk_toc(toc):
        for item in toc:
            if isinstance(item, epub.Link):
                titles.append(item.title)
            elif isinstance(item, tuple):
                section, children = item
                titles.append(section.title)
                _walk_toc(children)

    _walk_toc(book.toc)
    return titles
