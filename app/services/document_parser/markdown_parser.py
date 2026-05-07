import re
import logging
from pathlib import Path
from app.services.document_parser.models import ParsedDocument

logger = logging.getLogger("paper_reader")

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CODE_BLOCK_RE = re.compile(r"(```[\s\S]*?```)", re.MULTILINE)
_TAG_RE = re.compile(r"(?:^|\s)#([a-zA-Z][\w-]*)")


def parse_markdown(file_path: str) -> ParsedDocument:
    doc = ParsedDocument(raw_path=file_path)

    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        doc.parse_status = "failed"
        doc.parse_errors.append(f"无法读取文件: {e}")
        return doc

    doc.content = content

    frontmatter = {}
    body = content
    fm_match = _FRONTMATTER_RE.match(content)
    if fm_match:
        fm_text = fm_match.group(1)
        body = content[fm_match.end() :]
        try:
            import yaml

            frontmatter = yaml.safe_load(fm_text) or {}
        except Exception as e:
            doc.parse_errors.append(f"YAML frontmatter 解析失败: {e}")
            frontmatter = {}

    doc.title = frontmatter.get("title", "") or Path(file_path).stem
    authors_val = frontmatter.get("authors", frontmatter.get("author", ""))
    if isinstance(authors_val, list):
        doc.authors = [str(a) for a in authors_val]
    elif isinstance(authors_val, str) and authors_val:
        doc.authors = [a.strip() for a in re.split(r"[,;&]|\band\b", authors_val) if a.strip()]

    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    inline_tags = _TAG_RE.findall(body)
    all_tags = list(dict.fromkeys(tags + inline_tags))

    doc.metadata = {
        "frontmatter": frontmatter,
        "tags": all_tags,
    }

    code_blocks = {}
    placeholder_idx = 0
    def _replace_code_block(m):
        nonlocal placeholder_idx
        key = f"__CODE_BLOCK_{placeholder_idx}__"
        code_blocks[key] = m.group(1)
        placeholder_idx += 1
        return key

    body_no_code = _CODE_BLOCK_RE.sub(_replace_code_block, body)

    heading_positions = []
    for m in _HEADING_RE.finditer(body_no_code):
        level = len(m.group(1))
        title = m.group(2).strip()
        heading_positions.append((m.start(), level, title))

    if not heading_positions:
        section_content = body.strip()
        section_type = "code" if body.strip().startswith("```") else "text"
        doc.sections.append(
            {
                "level": 1,
                "title": doc.title,
                "content": section_content,
                "type": section_type,
            }
        )
    else:
        pre_heading = body_no_code[: heading_positions[0][0]].strip()
        if pre_heading:
            doc.sections.append(
                {
                    "level": 0,
                    "title": "",
                    "content": pre_heading,
                    "type": "text",
                }
            )

        for i, (pos, level, title) in enumerate(heading_positions):
            end_pos = heading_positions[i + 1][0] if i + 1 < len(heading_positions) else len(body_no_code)
            section_text = body_no_code[pos:end_pos].strip()

            for key, code in code_blocks.items():
                section_text = section_text.replace(key, code)

            is_code_section = bool(_CODE_BLOCK_RE.search(section_text)) and len(
                _CODE_BLOCK_RE.findall(section_text)
            ) >= len(section_text.strip()) * 0.5

            doc.sections.append(
                {
                    "level": level,
                    "title": title,
                    "content": section_text,
                    "type": "code" if is_code_section else "text",
                }
            )

    doc.parse_status = "success"
    return doc
