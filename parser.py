"""EPUB/MOBI/PDF 解析 + 文本分块。"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import ebooklib
import pdfplumber
from bs4 import BeautifulSoup
from ebooklib import epub

from config import CHUNK_HARD_LIMIT, CHUNK_MAX_CHARS
from models import BookData, Chapter

logger = logging.getLogger(__name__)

KINDLE_EXTENSIONS = {".mobi", ".azw", ".azw3", ".kf8"}

# ── 预编译正则（O(1) 匹配）────────────────────────────────────────────
_PARA_BOUNDARY_RE = re.compile(r"\n\s*\n")
_SENTENCE_BOUNDARY_RE = re.compile(r"[。！？.!?]")


def parse_epub(file_path: Path) -> BookData:
    """读取 EPUB，提取元数据和正文，按章节分块。"""
    book = epub.read_epub(str(file_path))

    title = _get_metadata(book, "title", file_path.stem)
    author = _get_metadata(book, "creator", "Unknown")

    chapters: list[Chapter] = []
    toc_titles = _extract_toc_titles(book)

    for item in _iter_documents_in_spine_order(book):
        try:
            html_content = item.get_content().decode("utf-8", errors="replace")
            text = _strip_html(html_content)
            if not text.strip():
                continue

            # 跳过纯目录页面
            if _is_toc_page(text):
                continue

            # 清理元数据行
            text = _clean_metadata_lines(text)
            if not text.strip():
                continue

            # 从 HTML 提取真实标题，而非依赖 TOC 索引
            chapter_title = _extract_title_from_html(html_content, text, toc_titles)
            chunks = chunk_text(text, CHUNK_MAX_CHARS)
            if chunks:
                chapters.append(Chapter(title=chapter_title, chunks=chunks))
        except Exception as e:
            logger.warning(f"  跳过文档项 {item.get_name()}: {e}")
            continue

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
    if suffix in KINDLE_EXTENSIONS:
        epub_path = convert_mobi_to_epub(file_path)
        return parse_epub(epub_path)
    if suffix == ".pdf":
        return parse_pdf(file_path)
    return parse_epub(file_path)


def convert_mobi_to_epub(mobi_path: Path) -> Path:
    """调用 calibre ebook-convert 将 MOBI 转为 EPUB。"""
    epub_path = mobi_path.with_suffix(".epub")
    if epub_path.exists() and epub_path.stat().st_mtime >= mobi_path.stat().st_mtime:
        return epub_path

    try:
        result = subprocess.run(
            ["ebook-convert", str(mobi_path), str(epub_path)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "未找到 `ebook-convert` 命令。MOBI/AZW 解析依赖 Calibre。"
            "请先安装 Calibre 并确保 `ebook-convert` 在 PATH 中。"
        ) from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or "未知错误"
        raise RuntimeError(f"MOBI/AZW 转换失败: {detail}")

    return epub_path


def chunk_text(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    r"""滑动窗口 + 自然边界分块。单块优先 ≤ max_chars，绝对不超过 CHUNK_HARD_LIMIT。

    策略：
    1. 在 max_chars 窗口内从后往前找段落边界 (\n\s*\n) — 最高优先级
    2. 在 max_chars 窗口内从后往前找句子边界 (。！？.!?) — 次优先级
    3. max_chars 内无边界时，向后扩展到 CHUNK_HARD_LIMIT 找最近边界
    4. 900 字内仍无边界，硬切在 CHUNK_HARD_LIMIT（极端情况兜底）
    """
    if not text:
        return []

    soft = max_chars
    hard = CHUNK_HARD_LIMIT
    chunks: list[str] = []
    pos = 0
    n = len(text)

    while pos < n:
        remaining = n - pos
        if remaining <= soft:
            chunk = text[pos:n].strip()
            if chunk:
                chunks.append(chunk)
            break

        # 一次扫描 [pos, pos+hard) 的范围
        big_window = text[pos : pos + min(hard, remaining)]
        para_matches = list(_PARA_BOUNDARY_RE.finditer(big_window))
        sent_matches = list(_SENTENCE_BOUNDARY_RE.finditer(big_window))

        # 策略1：在 soft limit 内找段落边界，取最后一个
        soft_para = [m for m in para_matches if m.end() <= soft]
        if soft_para:
            split_at = pos + soft_para[-1].end()
            chunks.append(text[pos:split_at].strip())
            pos = split_at
            continue

        # 策略2：在 soft limit 内找句子边界，取最后一个
        soft_sent = [m for m in sent_matches if m.end() <= soft]
        if soft_sent:
            sent_match = soft_sent[-1]
            # 防御：若最后一个边界产生的 chunk 太短（< 30% soft），尝试倒数第二个
            if sent_match.end() < soft * 0.3 and len(soft_sent) >= 2:
                second_last = soft_sent[-2]
                if second_last.end() >= soft * 0.5:
                    sent_match = second_last
            split_at = pos + sent_match.end()
            chunks.append(text[pos:split_at].strip())
            pos = split_at
            continue

        # 策略3：soft limit 内无边界 —— 在 soft~hard 之间找最近边界
        hard_para = [m for m in para_matches if soft < m.end() <= hard]
        hard_sent = [m for m in sent_matches if soft < m.end() <= hard]

        best_boundary = None
        if hard_para:
            best_boundary = hard_para[0].end()
        if hard_sent:
            sent_pos = hard_sent[0].end()
            if best_boundary is None or sent_pos < best_boundary:
                best_boundary = sent_pos

        if best_boundary:
            split_at = pos + best_boundary
            chunks.append(text[pos:split_at].strip())
            pos = split_at
            continue

        # 策略4：900 字内真的没有任何边界（极端情况）
        split_at = pos + min(hard, remaining)
        chunks.append(text[pos:split_at].strip())
        pos = split_at

    return [c for c in chunks if c]


def _strip_html(html: str) -> str:
    """剥离 HTML 标签，提取纯文本。"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _extract_title_from_html(html: str, text: str, toc_titles: list[str]) -> str:
    """从 HTML 内容中提取章节标题。

    优先级：h1-h3 标签 > TOC 标题匹配 > 正文第一行
    """
    soup = BeautifulSoup(html, "html.parser")

    # 优先从 heading 标签提取
    for tag_name in ("h1", "h2", "h3"):
        heading = soup.find(tag_name)
        if heading:
            title = heading.get_text(strip=True)
            if title and len(title) < 100:
                return title

    # 尝试从 TOC 中匹配（通过 href）
    # fallback: 用正文前 50 字作为标题
    first_line = text.strip().split("\n")[0].strip()
    if first_line and len(first_line) < 80:
        return first_line

    return "未命名章节"


# 元数据行关键词（需要从正文中移除的行）
_METADATA_LINE_KEYWORDS = [
    "来源于",
    "Published by",
    "Copyright",
    "听报道",
    "回到目录",
    "Back to TOC",
    "返回目录",
    "返回上级",
    "相关文章：",
    "更多报道详见：",
]

# 最小有效文本长度
_MIN_TEXT_LENGTH = 100


def _is_toc_page(text: str) -> bool:
    """检测是否为纯目录页面（封面、空白页等）。"""
    # 太短的文本可能是封面/空白页
    if len(text.strip()) < _MIN_TEXT_LENGTH:
        return True

    return False


def _clean_metadata_lines(text: str) -> str:
    """移除文本中的元数据行。"""
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        # 跳过包含元数据关键词的行
        if any(keyword in line for keyword in _METADATA_LINE_KEYWORDS):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


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


def _iter_documents_in_spine_order(book: epub.EpubBook) -> list:
    """按 spine 阅读顺序返回 ITEM_DOCUMENT 列表。

    Why: `get_items_of_type` 返回的是 manifest 顺序（通常按文件名），
    并不一定等于阅读顺序。EPUB 的真正阅读顺序由 spine 决定，否则章节会错位。
    """
    items: list = []
    seen: set[str] = set()

    for spine_entry in book.spine:
        idref = spine_entry[0] if isinstance(spine_entry, (tuple, list)) else spine_entry
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        items.append(item)
        seen.add(item.get_id())

    # Fallback: spine 缺失或为空时，回退到 manifest 顺序
    if not items:
        return list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))

    # 补漏：把 spine 未收录但属于 manifest 的文档项追加到末尾
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        if item.get_id() not in seen:
            items.append(item)

    return items
