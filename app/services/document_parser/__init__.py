import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.services.document_parser.models import ParsedDocument
from app.services.document_parser.pdf_parser import parse_pdf
from app.services.document_parser.markdown_parser import parse_markdown
from app.services.document_parser.epub_parser import parse_epub
from app.services.document_parser.docx_parser import parse_docx
from app.services.document_parser.latex_parser import parse_latex

logger = logging.getLogger("paper_reader")

FORMAT_MAP = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".epub": "epub",
    ".docx": "docx",
    ".doc": "docx",
    ".tex": "latex",
    ".latex": "latex",
}

_PARSER_DISPATCH = {
    "pdf": parse_pdf,
    "markdown": parse_markdown,
    "epub": parse_epub,
    "docx": parse_docx,
    "latex": parse_latex,
}


class DocumentParser:
    def parse(self, file_path: str, format_hint: str = None) -> ParsedDocument:
        fmt = format_hint or self._detect_format(file_path)
        if not fmt:
            doc = ParsedDocument(
                raw_path=file_path,
                parse_status="failed",
                parse_errors=[f"无法识别文件格式: {file_path}"],
            )
            return doc

        parser_fn = _PARSER_DISPATCH.get(fmt)
        if not parser_fn:
            doc = ParsedDocument(
                raw_path=file_path,
                parse_status="failed",
                parse_errors=[f"不支持的格式: {fmt}"],
            )
            return doc

        try:
            return parser_fn(file_path)
        except Exception as e:
            logger.error(f"解析文件失败 {file_path}: {e}")
            return ParsedDocument(
                raw_path=file_path,
                parse_status="failed",
                parse_errors=[str(e)],
            )

    def parse_batch(
        self, file_paths: list[str], max_workers: int = 2
    ) -> list[ParsedDocument]:
        results: dict[int, ParsedDocument] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.parse, fp): idx
                for idx, fp in enumerate(file_paths)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = ParsedDocument(
                        raw_path=file_paths[idx],
                        parse_status="failed",
                        parse_errors=[str(e)],
                    )
        return [results[i] for i in range(len(file_paths))]

    @staticmethod
    def _detect_format(file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        return FORMAT_MAP.get(ext, "")
