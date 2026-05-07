import re
import logging
from pathlib import Path
from app.services.document_parser.models import ParsedDocument

logger = logging.getLogger("paper_reader")

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&(\w+);")
_HTML_ENTITIES = {
    "nbsp": " ",
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "quot": '"',
    "apos": "'",
    "mdash": "\u2014",
    "ndash": "\u2013",
    "hellip": "\u2026",
}


def _html_to_text(html: str) -> str:
    text = _HTML_TAG_RE.sub("", html)
    for entity, char in _HTML_ENTITIES.items():
        text = text.replace(f"&{entity};", char)
    text = text.replace("&#", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _decode_html_entities(text: str) -> str:
    def _replace_entity(m):
        name = m.group(1)
        return _HTML_ENTITIES.get(name, m.group(0))
    return _HTML_ENTITY_RE.sub(_replace_entity, text)


def parse_epub(file_path: str) -> ParsedDocument:
    doc = ParsedDocument(raw_path=file_path)

    try:
        import ebooklib
        from ebooklib import epub
    except ImportError:
        doc.parse_status = "failed"
        doc.parse_errors.append("ebooklib 未安装，无法解析 EPUB")
        return doc

    try:
        book = epub.read_epub(file_path)
    except Exception as e:
        doc.parse_status = "failed"
        doc.parse_errors.append(f"无法打开 EPUB 文件: {e}")
        return doc

    try:
        doc.title = _decode_html_entities(book.get_metadata("DC", "title")[0][0]) if book.get_metadata("DC", "title") else ""
        author_list = [a[0] for a in book.get_metadata("DC", "creator")]
        doc.authors = [_decode_html_entities(a) for a in author_list]

        publisher = book.get_metadata("DC", "publisher")
        language = book.get_metadata("DC", "language")
        identifier = book.get_metadata("DC", "identifier")

        doc.metadata = {
            "publisher": _decode_html_entities(publisher[0][0]) if publisher else "",
            "language": language[0][0] if language else "",
            "identifier": identifier[0][0] if identifier else "",
        }

        toc = book.toc
        toc_titles = {}
        for idx, item in enumerate(toc):
            if isinstance(item, tuple):
                section, children = item
                toc_titles[section.href.split("#")[0]] = _decode_html_entities(section.title)
                for child in children:
                    toc_titles[child.href.split("#")[0]] = _decode_html_entities(child.title)
            else:
                toc_titles[item.href.split("#")[0]] = _decode_html_entities(item.title)

        all_text_parts = []
        spine_items = book.spine

        for spine_id, linear in spine_items:
            item = book.get_item_with_id(spine_id)
            if item is None:
                continue
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue

            html_content = item.get_content().decode("utf-8", errors="replace")
            plain_text = _html_to_text(html_content)

            if not plain_text.strip():
                continue

            href = item.get_name()
            chapter_title = toc_titles.get(href, "")

            if chapter_title:
                doc.sections.append(
                    {
                        "level": 2,
                        "title": chapter_title,
                        "content": plain_text,
                        "type": "text",
                    }
                )
            else:
                doc.sections.append(
                    {
                        "level": 3,
                        "title": "",
                        "content": plain_text,
                        "type": "text",
                    }
                )

            all_text_parts.append(plain_text)

        doc.content = "\n\n".join(all_text_parts)

        if not doc.title:
            doc.title = Path(file_path).stem

        if not all_text_parts:
            doc.parse_status = "partial"
            doc.parse_errors.append("EPUB 内容提取为空")
        else:
            doc.parse_status = "success"

    except Exception as e:
        doc.parse_status = "failed"
        doc.parse_errors.append(f"EPUB 解析异常: {e}")

    return doc
