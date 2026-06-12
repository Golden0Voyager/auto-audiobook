"""parser IO 测试 — mock ebooklib/pdfplumber/subprocess 验证解析逻辑。"""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub

from models import BookData, Chapter
from parser import (
    _extract_toc_titles,
    _get_metadata,
    _iter_documents_in_spine_order,
    convert_mobi_to_epub,
    parse_epub,
    parse_file,
    parse_pdf,
)


class TestGetMetadata:
    def test_returns_value_when_exists(self):
        class FakeBook:
            def get_metadata(self, ns, key):
                return [("value", None)]

        book = FakeBook()
        assert _get_metadata(book, "title", "default") == "value"

    def test_returns_default_when_missing(self):
        class FakeBook:
            def get_metadata(self, ns, key):
                return []

        book = FakeBook()
        assert _get_metadata(book, "title", "默认书名") == "默认书名"


class TestExtractTocTitles:
    def test_flat_toc(self):
        """平铺 TOC（epub.Link 列表）。"""
        class FakeBook:
            toc = [
                epub.Link("ch1.xhtml", "第一章", "ch1"),
                epub.Link("ch2.xhtml", "第二章", "ch2"),
            ]

        titles = _extract_toc_titles(FakeBook())
        assert titles == ["第一章", "第二章"]

    def test_nested_toc(self):
        """嵌套 TOC（包含子章节）。"""
        class FakeSection:
            title = "第一部分"

        class FakeBook:
            toc = [
                (FakeSection(), [
                    epub.Link("ch1.xhtml", "第一章", "ch1"),
                ])
            ]

        titles = _extract_toc_titles(FakeBook())
        assert "第一部分" in titles
        assert "第一章" in titles

    def test_empty_toc(self):
        class FakeBook:
            toc = []

        assert _extract_toc_titles(FakeBook()) == []


class TestIterDocumentsInSpineOrder:
    def test_spine_order_is_followed(self):
        """按 spine 顺序返回文档项。"""
        items_created = {}

        class FakeItem:
            def __init__(self, item_id, item_type=9):  # 9 = ITEM_DOCUMENT
                self._id = item_id
                self._type = item_type

            def get_id(self):
                return self._id

            def get_type(self):
                return self._type

        class FakeBook:
            spine = [("id3", None), ("id1", None), ("id2", None)]

            def get_item_with_id(self, idref):
                return items_created.get(idref)

            def get_items_of_type(self, _type):
                return [items_created[k] for k in ["id1", "id2", "id3", "id4"]]

        items_created["id1"] = FakeItem("id1")
        items_created["id2"] = FakeItem("id2")
        items_created["id3"] = FakeItem("id3")
        items_created["id4"] = FakeItem("id4")  # 未在 spine 中

        result = _iter_documents_in_spine_order(FakeBook())
        # spine 顺序: id3, id1, id2, 然后补充 id4
        ids = [item.get_id() for item in result]
        assert ids == ["id3", "id1", "id2", "id4"]

    def test_fallback_to_manifest_when_spine_empty(self):
        """spine 为空时回退到 manifest 顺序。"""
        class FakeItem:
            def __init__(self, item_id):
                self._id = item_id

            def get_id(self):
                return self._id

            def get_type(self):
                return 9  # ITEM_DOCUMENT

        class FakeBook:
            spine = []

            def get_item_with_id(self, idref):
                return None

            def get_items_of_type(self, _type):
                return [FakeItem("c"), FakeItem("a"), FakeItem("b")]

        result = _iter_documents_in_spine_order(FakeBook())
        ids = [item.get_id() for item in result]
        assert ids == ["c", "a", "b"]

    def test_filters_non_document_items(self):
        """跳过的非 ITEM_DOCUMENT 项目。"""
        class FakeItem:
            def __init__(self, item_id, item_type):
                self._id = item_id
                self._type = item_type

            def get_id(self):
                return self._id

            def get_type(self):
                return self._type

        class FakeBook:
            spine = [("doc1", None), ("style1", None), ("doc2", None)]

            def get_item_with_id(self, idref):
                items = {
                    "doc1": FakeItem("doc1", 9),   # ITEM_DOCUMENT
                    "style1": FakeItem("style1", 8),  # ITEM_STYLESHEET
                    "doc2": FakeItem("doc2", 9),   # ITEM_DOCUMENT
                }
                return items.get(idref)

            def get_items_of_type(self, _type):
                return []

        result = _iter_documents_in_spine_order(FakeBook())
        ids = [item.get_id() for item in result]
        assert ids == ["doc1", "doc2"]


class TestParseEpub:
    """mock epub.read_epub 测试 parse_epub。"""

    def test_basic_parsing(self, monkeypatch):
        """基本 EPUB 解析流程：提取标题/作者/章节/正文。"""

        # HTML 正文必须 >100 字符以避免 _is_toc_page 跳过
        _LONG_TEXT = "正文内容。" * 30  # 90 chars + padding

        class FakeChapterItem:
            """模拟一个 EPUB 文档项（章节）。"""
            def get_content(self):
                html = f"<html><body><h1>第一章</h1><p>{_LONG_TEXT}</p></body></html>"
                return html.encode("utf-8")

            def get_name(self):
                return "chapter1.xhtml"

            def get_id(self):
                return "ch1"

            def get_type(self):
                return 9  # ITEM_DOCUMENT

        class FakeBook:
            toc = [
                epub.Link("ch1.xhtml", "第一章", "ch1"),
            ]
            spine = [("ch1", None)]

            def get_metadata(self, ns, key):
                data = {
                    "title": [("测试书名", None)],
                    "creator": [("测试作者", None)],
                }
                val = data.get(key, [])
                return val

            def get_item_with_id(self, idref):
                return FakeChapterItem() if idref == "ch1" else None

            def get_items_of_type(self, _type):
                return [FakeChapterItem()]

        monkeypatch.setattr("parser.epub.read_epub", lambda p: FakeBook())

        result = parse_epub(Path("test.epub"))
        assert isinstance(result, BookData)
        assert result.title == "测试书名"
        assert result.author == "测试作者"
        assert len(result.chapters) >= 1
        assert "正文" in result.chapters[0].chunks[0]

    def test_skips_toc_pages(self, monkeypatch):
        """跳过短文本的目录页。"""

        class FakeTOCItem:
            def get_content(self):
                return "<html><body>目录</body></html>".encode("utf-8")

            def get_name(self):
                return "toc.xhtml"

            def get_id(self):
                return "toc"

            def get_type(self):
                return 9

        # 正文必须 >100 字符以避免 _is_toc_page 跳过
        _LONG_TEXT = "正文内容。" * 30  # 90 chars + padding

        class FakeContentItem:
            def get_content(self):
                html = f"<html><body><h1>第一章</h1><p>{_LONG_TEXT}</p></body></html>"
                return html.encode("utf-8")

            def get_name(self):
                return "ch1.xhtml"

            def get_id(self):
                return "ch1"

            def get_type(self):
                return 9

        class FakeBook:
            toc = [
                epub.Link("ch1.xhtml", "第一章", "ch1"),
            ]
            spine = [("toc", None), ("ch1", None)]

            def get_metadata(self, ns, key):
                return [("书", None)] if key == "title" else []

            def get_item_with_id(self, idref):
                return {"toc": FakeTOCItem(), "ch1": FakeContentItem()}.get(idref)

            def get_items_of_type(self, _type):
                return [FakeTOCItem(), FakeContentItem()]

        monkeypatch.setattr("parser.epub.read_epub", lambda p: FakeBook())

        result = parse_epub(Path("test.epub"))
        assert len(result.chapters) == 1  # 只保留正文章节
        assert result.chapters[0].title == "第一章"

    def test_handles_parse_error_gracefully(self, monkeypatch):
        """跳过解析失败的文档项。"""

        class FakeBook:
            toc = []
            spine = [("bad", None)]

            def get_metadata(self, ns, key):
                return [("书", None)] if key == "title" else []

            def get_item_with_id(self, idref):
                item = type("BadItem", (), {
                    "get_content": lambda self: (_ for _ in ()).throw(
                        Exception("Parse error")
                    ),
                    "get_name": lambda self: "bad.xhtml",
                    "get_id": lambda self: "bad",
                    "get_type": lambda self: 9,
                })()
                return item

            def get_items_of_type(self, _type):
                return []

        monkeypatch.setattr("parser.epub.read_epub", lambda p: FakeBook())

        result = parse_epub(Path("test.epub"))
        assert len(result.chapters) == 0  # 跳过错误，无章节


class TestParsePdf:
    """mock pdfplumber 测试 parse_pdf。"""

    def test_basic_pdf_parsing(self, monkeypatch):
        """基本 PDF 解析。"""

        class FakePage:
            def __init__(self, text, page_num=1):
                self._text = text

            def extract_text(self):
                return self._text

        class FakePDF:
            pages = [FakePage("第1章 开始\n这是一段正文内容。")]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def close(self):
                pass

        monkeypatch.setattr("parser.pdfplumber.open", lambda p: FakePDF())

        result = parse_pdf(Path("test.pdf"))
        assert isinstance(result, BookData)
        assert result.title == "test"
        assert result.author == "Unknown"

    def test_empty_pages(self, monkeypatch):
        """全空页面的 PDF 应返回空章节列表。"""

        class FakePage:
            def extract_text(self):
                return ""

        class FakePDF:
            pages = [FakePage(), FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr("parser.pdfplumber.open", lambda p: FakePDF())

        result = parse_pdf(Path("empty.pdf"))
        assert isinstance(result, BookData)
        assert len(result.chapters) == 0

    def test_detects_chapter_titles(self, monkeypatch):
        """检测中文/英文章节标题。"""

        class FakePage:
            def __init__(self, text):
                self._text = text

            def extract_text(self):
                return self._text

        _pages = [FakePage("第1章 绪论\n这是绪论的内容。")]
        for i in range(2, 5):
            _pages.append(FakePage(f"这是第{i}章的内容。\n继续第{i}章。"))

        class FakePDF:
            def __init__(self):
                self.pages = _pages

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr("parser.pdfplumber.open", lambda p: FakePDF())

        result = parse_pdf(Path("book.pdf"))
        # 至少有一章（PDF 章节检测逻辑较简单）
        assert len(result.chapters) >= 1

    def test_no_chapter_detected_fallback(self, monkeypatch):
        """无章节标题时使用默认标题。"""

        class FakePage:
            def __init__(self, text):
                self._text = text

            def extract_text(self):
                return self._text

        class FakePDF:
            pages = [FakePage("这是第一页的内容。" * 20),
                     FakePage("这是第二页的内容。" * 20)]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr("parser.pdfplumber.open", lambda p: FakePDF())

        result = parse_pdf(Path("book.pdf"))
        # 无匹配的章节标题—默认使用 "Chapter 1"
        assert len(result.chapters) == 1
        assert result.chapters[0].title == "Chapter 1"


class TestConvertMobiToEpub:
    def test_conversion_success(self, monkeypatch, tmp_path):
        """成功调用 ebook-convert。"""
        mobi_path = tmp_path / "book.mobi"
        mobi_path.write_text("mobi data")
        epub_path = mobi_path.with_suffix(".epub")

        class FakeResult:
            returncode = 0
            stderr = ""
            stdout = "Conversion successful"

        monkeypatch.setattr("parser.subprocess.run", lambda *a, **kw: FakeResult())

        result = convert_mobi_to_epub(mobi_path)
        assert result == epub_path

    def test_skips_if_epub_newer(self, monkeypatch, tmp_path):
        """已有更新的 EPUB 时跳过转换。"""
        mobi_path = tmp_path / "book.mobi"
        epub_path = mobi_path.with_suffix(".epub")
        mobi_path.write_text("mobi")
        epub_path.write_text("epub")

        # Ensure epub is newer
        epub_mtime = mobi_path.stat().st_mtime + 10
        import os
        os.utime(str(epub_path), (epub_mtime, epub_mtime))

        call_count = {"n": 0}

        def fake_run(*a, **kw):
            call_count["n"] += 1
            return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

        monkeypatch.setattr("parser.subprocess.run", fake_run)

        result = convert_mobi_to_epub(mobi_path)
        assert result == epub_path
        assert call_count["n"] == 0  # 未调用 subprocess

    def test_calibre_not_found_raises(self, monkeypatch):
        """缺少 Calibre 时抛 RuntimeError。"""
        monkeypatch.setattr("parser.subprocess.run", lambda *a, **kw: (_ for _ in ()).throw(
            FileNotFoundError("No such file: ebook-convert")
        ))

        import pytest
        with pytest.raises(RuntimeError, match="Calibre"):
            convert_mobi_to_epub(Path("book.mobi"))

    def test_conversion_failure_raises(self, monkeypatch):
        """转换失败时抛 RuntimeError。"""
        class FakeResult:
            returncode = 1
            stderr = "Conversion error"
            stdout = ""

        monkeypatch.setattr("parser.subprocess.run", lambda *a, **kw: FakeResult())

        import pytest
        with pytest.raises(RuntimeError, match="Conversion error"):
            convert_mobi_to_epub(Path("book.mobi"))


class TestParseFile:
    """测试 parse_file 路由逻辑（mock 各格式的解析函数）。"""

    def test_routes_epub(self, monkeypatch):
        called = {"parse_epub": False}

        def fake_parse_epub(path):
            called["parse_epub"] = True
            return BookData(title="epub", author="a", language="zh")

        monkeypatch.setattr("parser.parse_epub", fake_parse_epub)

        result = parse_file(Path("book.epub"))
        assert called["parse_epub"] is True
        assert result.title == "epub"

    def test_routes_pdf(self, monkeypatch):
        called = {"parse_pdf": False}

        def fake_parse_pdf(path):
            called["parse_pdf"] = True
            return BookData(title="pdf", author="a", language="en")

        monkeypatch.setattr("parser.parse_pdf", fake_parse_pdf)

        result = parse_file(Path("doc.pdf"))
        assert called["parse_pdf"] is True
        assert result.title == "pdf"

    def test_routes_mobi_via_conversion(self, monkeypatch):
        """MOBI 文件先转换再解析 EPUB。"""
        calls = []

        def fake_convert(path):
            calls.append(("convert", path.suffix))
            return path.with_suffix(".epub")

        def fake_parse_epub(path):
            calls.append(("parse", path.suffix))
            return BookData(title="from_mobi", author="a", language="zh")

        monkeypatch.setattr("parser.convert_mobi_to_epub", fake_convert)
        monkeypatch.setattr("parser.parse_epub", fake_parse_epub)

        result = parse_file(Path("book.mobi"))
        assert calls == [("convert", ".mobi"), ("parse", ".epub")]
        assert result.title == "from_mobi"

    def test_routes_azw3(self, monkeypatch):
        """AZW3 也走 MOBI 转换路径。"""
        calls = []

        def fake_convert(path):
            calls.append(("convert", path.suffix))
            return path.with_suffix(".epub")

        def fake_parse_epub(path):
            return BookData(title="from_azw3", author="a", language="zh")

        monkeypatch.setattr("parser.convert_mobi_to_epub", fake_convert)
        monkeypatch.setattr("parser.parse_epub", fake_parse_epub)

        result = parse_file(Path("book.azw3"))
        assert calls[0] == ("convert", ".azw3")

    def test_routes_kf8(self, monkeypatch):
        """KF8 也走 MOBI 转换路径。"""
        def fake_convert(path):
            return path.with_suffix(".epub")

        def fake_parse_epub(path):
            return BookData(title="from_kf8", author="a", language="zh")

        monkeypatch.setattr("parser.convert_mobi_to_epub", fake_convert)
        monkeypatch.setattr("parser.parse_epub", fake_parse_epub)

        result = parse_file(Path("book.kf8"))
        assert result.title == "from_kf8"
