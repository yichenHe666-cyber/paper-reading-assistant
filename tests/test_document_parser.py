import tempfile
from pathlib import Path

from app.services.document_parser import DocumentParser, FORMAT_MAP
from app.services.document_parser.models import ParsedDocument
from app.services.document_parser.pdf_parser import is_garbled_text
from app.services.document_parser.markdown_parser import parse_markdown
from app.services.document_parser.latex_parser import parse_latex


def test_parsed_document_dataclass():
    doc = ParsedDocument()
    assert doc.title == ""
    assert doc.authors == []
    assert doc.content == ""
    assert doc.sections == []
    assert doc.metadata == {}
    assert doc.raw_path == ""
    assert doc.parse_status == "success"
    assert doc.parse_errors == []

    doc2 = ParsedDocument(
        title="Test",
        authors=["Alice", "Bob"],
        content="Hello",
        sections=[{"level": 1, "title": "Intro", "content": "Hi", "type": "text"}],
        metadata={"key": "value"},
        raw_path="/tmp/test.md",
        parse_status="failed",
        parse_errors=["err1"],
    )
    assert doc2.title == "Test"
    assert doc2.authors == ["Alice", "Bob"]
    assert doc2.content == "Hello"
    assert len(doc2.sections) == 1
    assert doc2.metadata["key"] == "value"
    assert doc2.raw_path == "/tmp/test.md"
    assert doc2.parse_status == "failed"
    assert doc2.parse_errors == ["err1"]


def test_detect_format_pdf():
    parser = DocumentParser()
    assert parser._detect_format("paper.pdf") == "pdf"
    assert parser._detect_format("PAPER.PDF") == "pdf"


def test_detect_format_markdown():
    parser = DocumentParser()
    assert parser._detect_format("notes.md") == "markdown"
    assert parser._detect_format("notes.markdown") == "markdown"


def test_detect_format_epub():
    parser = DocumentParser()
    assert parser._detect_format("book.epub") == "epub"


def test_detect_format_docx():
    parser = DocumentParser()
    assert parser._detect_format("report.docx") == "docx"
    assert parser._detect_format("report.doc") == "docx"


def test_detect_format_latex():
    parser = DocumentParser()
    assert parser._detect_format("paper.tex") == "latex"
    assert parser._detect_format("paper.latex") == "latex"


def test_parse_nonexistent_file():
    parser = DocumentParser()
    result = parser.parse("/nonexistent/path/test.pdf")
    assert result.parse_status == "failed"
    assert len(result.parse_errors) > 0


def test_parse_unsupported_format():
    parser = DocumentParser()
    result = parser.parse("data.xyz")
    assert result.parse_status == "failed"
    assert any("格式" in e for e in result.parse_errors)


def test_parse_batch_empty():
    parser = DocumentParser()
    results = parser.parse_batch([])
    assert results == []


def test_is_garbled_text():
    assert is_garbled_text("") is False
    assert is_garbled_text("   ") is False
    assert is_garbled_text("Hello world") is False
    assert is_garbled_text("中文测试内容") is False

    garbled = "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0e\x0f"
    assert is_garbled_text(garbled) is True

    mixed = "Hello\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b"
    assert is_garbled_text(mixed) is True

    assert is_garbled_text("Line1\nLine2\tTab") is False


def test_markdown_parser_with_frontmatter():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write("---\n")
        f.write("title: Test Document\n")
        f.write("authors:\n")
        f.write("  - Alice\n")
        f.write("  - Bob\n")
        f.write("tags: [test, knowledge]\n")
        f.write("---\n\n")
        f.write("# Introduction\n\n")
        f.write("This is the intro.\n\n")
        f.write("## Methods\n\n")
        f.write("Some methods here.\n")
        tmp_path = f.name

    try:
        result = parse_markdown(tmp_path)
        assert result.parse_status == "success"
        assert result.title == "Test Document"
        assert "Alice" in " ".join(result.authors)
        assert "Bob" in " ".join(result.authors)
        assert "Introduction" in result.content
        assert len(result.sections) >= 1
        assert result.metadata.get("frontmatter") is not None
        assert "test" in result.metadata.get("tags", [])
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_latex_parser_basic():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".tex", delete=False, encoding="utf-8"
    ) as f:
        f.write("\\documentclass{article}\n")
        f.write("\\title{Test LaTeX Paper}\n")
        f.write("\\author{Alice \\and Bob}\n")
        f.write("\\begin{document}\n")
        f.write("\\maketitle\n")
        f.write("\\begin{abstract}\n")
        f.write("This is the abstract.\n")
        f.write("\\end{abstract}\n")
        f.write("\\section{Introduction}\n")
        f.write("Intro content here.\n")
        f.write("\\section{Methods}\n")
        f.write("Methods content here.\n")
        f.write("\\end{document}\n")
        tmp_path = f.name

    try:
        result = parse_latex(tmp_path)
        assert result.parse_status == "success"
        assert "Test LaTeX Paper" in result.title
        assert "Alice" in " ".join(result.authors)
        assert "Bob" in " ".join(result.authors)
        assert len(result.sections) >= 1
        assert result.metadata.get("abstract") != ""
        assert "Introduction" in [s["title"] for s in result.sections]
    finally:
        Path(tmp_path).unlink(missing_ok=True)
