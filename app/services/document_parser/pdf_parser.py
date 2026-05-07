import unicodedata
import logging
from app.services.document_parser.models import ParsedDocument

logger = logging.getLogger("paper_reader")


def is_garbled_text(text: str, threshold: float = 0.3) -> bool:
    if not text.strip():
        return False
    bad_chars = sum(
        1
        for c in text
        if unicodedata.category(c).startswith("C") and c not in "\n\r\t"
    )
    return bad_chars / len(text) > threshold


def parse_pdf(file_path: str) -> ParsedDocument:
    doc = ParsedDocument(raw_path=file_path)
    try:
        import fitz
    except ImportError:
        doc.parse_status = "failed"
        doc.parse_errors.append("PyMuPDF (fitz) 未安装，无法解析 PDF")
        return doc

    try:
        pdf_doc = fitz.open(file_path)
    except Exception as e:
        doc.parse_status = "failed"
        doc.parse_errors.append(f"无法打开 PDF 文件: {e}")
        return doc

    try:
        meta = pdf_doc.metadata or {}
        doc.title = meta.get("title", "") or ""
        author_str = meta.get("author", "") or ""
        if author_str:
            doc.authors = [a.strip() for a in author_str.split(";") if a.strip()]

        doc.metadata = {
            "page_count": pdf_doc.page_count,
            "format": meta.get("format", ""),
            "creator": meta.get("creator", ""),
            "producer": meta.get("producer", ""),
            "subject": meta.get("subject", ""),
            "keywords": meta.get("keywords", ""),
        }

        text_parts = []
        for page_num in range(pdf_doc.page_count):
            page = pdf_doc[page_num]
            page_text = page.get_text()
            if is_garbled_text(page_text):
                doc.parse_errors.append(
                    f"第 {page_num + 1} 页文本提取异常，可能存在字体映射问题"
                )
                page_text = f"[第 {page_num + 1} 页文本提取异常，可能存在字体映射问题]"
            text_parts.append(page_text)

        pdf_doc.close()

        full_text = "\n\n".join(text_parts)
        doc.content = full_text

        if not full_text.strip():
            doc.parse_status = "partial"
            doc.parse_errors.append("PDF 文本提取结果为空")
        elif doc.parse_errors:
            doc.parse_status = "partial"
        else:
            doc.parse_status = "success"

        if doc.title and full_text.strip():
            doc.sections.append(
                {
                    "level": 1,
                    "title": doc.title,
                    "content": full_text,
                    "type": "text",
                }
            )

    except Exception as e:
        doc.parse_status = "failed"
        doc.parse_errors.append(f"PDF 解析异常: {e}")
        try:
            pdf_doc.close()
        except Exception:
            pass

    return doc
