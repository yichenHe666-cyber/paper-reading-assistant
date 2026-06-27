import re
import httpx
from pathlib import Path
from datetime import datetime
from app.config import get_settings

RAW_DIR = Path(get_settings().knowledge_base_path) / "raw" / "papers"


def fix_arxiv_url(pdf_url: str) -> str:
    abs_match = re.search(r'arxiv\.org/abs/([\w.\-]+)', pdf_url)
    if abs_match:
        return f'https://arxiv.org/pdf/{abs_match.group(1)}.pdf'
    if 'arxiv.org/pdf/' in pdf_url:
        if not pdf_url.endswith('.pdf'):
            return pdf_url + '.pdf'
        return pdf_url
    return pdf_url


def download_pdf(paper_id: str, pdf_url: str) -> dict:
    slug = re.sub(r'[<>:"/\\|?*]', '-', paper_id)[:80]
    pdf_path = RAW_DIR / f"{slug}.pdf"
    md_path = RAW_DIR / f"{slug}.md"
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    url = fix_arxiv_url(pdf_url)
    result = {"paper_id": paper_id, "pdf_url": url, "status": "pending"}

    try:
        if not pdf_path.exists():
            resp = httpx.get(url, timeout=60, follow_redirects=True)
            if resp.status_code != 200:
                return {**result, "status": "download_failed", "http_status": resp.status_code}
            pdf_path.write_bytes(resp.content)
            result["pdf_size_kb"] = round(len(resp.content) / 1024, 1)
        else:
            result["pdf_size_kb"] = round(pdf_path.stat().st_size / 1024, 1)

        result["status"] = "pdf_downloaded"
        result["pdf_path"] = str(pdf_path)

        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()
            full_text = "\n\n".join(text_parts)

            if full_text.strip():
                title_slug = slug[:60]
                md_content = f"""---
title: "{paper_id}"
source: {url}
extracted: {datetime.now().strftime('%Y-%m-%d %H:%M')}
pages: {len(text_parts)}
---

{full_text}
"""
                md_path.write_text(md_content, encoding="utf-8")
                result["status"] = "text_extracted"
                result["text_length"] = len(full_text)
                result["md_path"] = str(md_path)
            else:
                result["status"] = "extraction_empty"
        except ImportError:
            result["status"] = "pdf_downloaded"
            result["note"] = "pymupdf not installed"
        except Exception as e:
            result["status"] = "extraction_error"
            result["error"] = str(e)

    except httpx.TimeoutException:
        result["status"] = "download_timeout"
    except Exception as e:
        result["status"] = "download_failed"
        result["error"] = str(e)

    return result


def get_paper_text(paper_id: str) -> str:
    slug = re.sub(r'[<>:"\/\\|?*]', '-', paper_id)[:80]
    md_path = RAW_DIR / f"{slug}.md"
    if md_path.exists():
        return md_path.read_text(encoding="utf-8")
    return ""


def save_uploaded_pdf(paper_id: str, pdf_bytes: bytes) -> dict:
    """Save user-uploaded PDF and extract text."""
    slug = re.sub(r'[<>:"\/\\|?*]', '-', paper_id)[:80]
    pdf_path = RAW_DIR / f"{slug}.pdf"
    md_path = RAW_DIR / f"{slug}.md"
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    result = {"paper_id": paper_id, "status": "pending", "source": "user_upload"}

    try:
        pdf_path.write_bytes(pdf_bytes)
        result["pdf_size_kb"] = round(len(pdf_bytes) / 1024, 1)
        result["status"] = "pdf_saved"
        result["pdf_path"] = str(pdf_path)

        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()
            full_text = "\n\n".join(text_parts)

            if full_text.strip():
                md_content = f"""---
title: "{paper_id}"
source: user_upload
extracted: {datetime.now().strftime('%Y-%m-%d %H:%M')}
pages: {len(text_parts)}
---

{full_text}
"""
                md_path.write_text(md_content, encoding="utf-8")
                result["status"] = "text_extracted"
                result["text_length"] = len(full_text)
                result["md_path"] = str(md_path)
            else:
                result["status"] = "extraction_empty"
        except ImportError:
            result["status"] = "pdf_saved"
            result["note"] = "pymupdf not installed"
        except Exception as e:
            result["status"] = "extraction_error"
            result["error"] = str(e)

    except Exception as e:
        result["status"] = "save_failed"
        result["error"] = str(e)

    return result
