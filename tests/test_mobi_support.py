from __future__ import annotations

from pathlib import Path

import main
import parser


def test_scan_input_dir_is_case_insensitive(tmp_path: Path):
    (tmp_path / "book.MOBI").write_text("x", encoding="utf-8")
    (tmp_path / "book.AZW3").write_text("x", encoding="utf-8")
    (tmp_path / "book.PDF").write_text("x", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("x", encoding="utf-8")

    files = main._scan_input_dir(tmp_path)
    names = [p.name for p in files]

    assert names == ["book.AZW3", "book.MOBI", "book.PDF"]


def test_parse_file_routes_kindle_formats(monkeypatch):
    called = {}

    def fake_convert(path: Path) -> Path:
        called["convert"] = path
        return path.with_suffix(".epub")

    def fake_parse_epub(path: Path):
        called["parse_epub"] = path
        return "ok"

    monkeypatch.setattr(parser, "convert_mobi_to_epub", fake_convert)
    monkeypatch.setattr(parser, "parse_epub", fake_parse_epub)

    result = parser.parse_file(Path("/tmp/sample.AZW3"))
    assert result == "ok"
    assert called["convert"] == Path("/tmp/sample.AZW3")
    assert called["parse_epub"] == Path("/tmp/sample.epub")
