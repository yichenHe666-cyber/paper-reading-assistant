import re
import logging
from pathlib import Path
from app.services.document_parser.models import ParsedDocument

logger = logging.getLogger("paper_reader")

_TITLE_RE = re.compile(r"\\title\{([^}]+)\}")
_AUTHOR_RE = re.compile(r"\\author\{([^}]+)\}")
_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL)
_SECTION_RE = re.compile(r"^\\(section|subsection|subsubsection)\{([^}]+)\}", re.MULTILINE)
_MATH_ENV_RE = re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray)\*?\}(.*?)\\end\{\1\*?\}", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)")
_DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_BIBLIOGRAPHY_RE = re.compile(r"\\bibliography\{([^}]+)\}")
_BIBITEM_RE = re.compile(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}")
_CROSS_REF_RE = re.compile(r"\\ref\{([^}]+)\}")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")


def _strip_commands(text: str) -> str:
    text = re.sub(r"\\(?:textbf|textit|emph|underline|texttt)\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\(?:cite[tp]?)\{[^}]+\}", "", text)
    text = re.sub(r"\\(?:ref|eqref|autoref|pageref)\{([^}]+)\}", r"[\1]", text)
    text = re.sub(r"\\[a-zA-Z]+(?:\[[^\]]*\])?(?:\{[^}]*\})*", "", text)
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def parse_latex(file_path: str) -> ParsedDocument:
    doc = ParsedDocument(raw_path=file_path)

    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        doc.parse_status = "failed"
        doc.parse_errors.append(f"无法读取文件: {e}")
        return doc

    doc.content = content

    title_match = _TITLE_RE.search(content)
    if title_match:
        doc.title = _strip_commands(title_match.group(1))

    author_match = _AUTHOR_RE.search(content)
    if author_match:
        author_str = _strip_commands(author_match.group(1))
        doc.authors = [a.strip() for a in re.split(r"\\and|[,;&]|\band\b", author_str) if a.strip()]

    abstract_match = _ABSTRACT_RE.search(content)
    abstract_text = ""
    if abstract_match:
        abstract_text = _strip_commands(abstract_match.group(1))

    bibliography = _BIBLIOGRAPHY_RE.findall(content)
    bibitems = _BIBITEM_RE.findall(content)
    labels = _LABEL_RE.findall(content)
    refs = _CROSS_REF_RE.findall(content)

    doc.metadata = {
        "abstract": abstract_text,
        "bibliography_files": bibliography,
        "bibitems": bibitems,
        "labels": labels,
        "references": refs,
    }

    math_sections = []
    for m in _MATH_ENV_RE.finditer(content):
        math_sections.append(
            {
                "level": 0,
                "title": f"Math: {m.group(1)}",
                "content": m.group(0),
                "type": "math",
            }
        )

    inline_math_count = len(_INLINE_MATH_RE.findall(content))
    display_math_count = len(_DISPLAY_MATH_RE.findall(content))

    section_positions = []
    for m in _SECTION_RE.finditer(content):
        cmd = m.group(1)
        title = _strip_commands(m.group(2))
        level_map = {"section": 2, "subsection": 3, "subsubsection": 4}
        level = level_map.get(cmd, 2)
        section_positions.append((m.start(), level, title))

    if not section_positions:
        plain_text = _strip_commands(content)
        doc.sections.append(
            {
                "level": 1,
                "title": doc.title or Path(file_path).stem,
                "content": plain_text,
                "type": "text",
            }
        )
    else:
        pre_section = content[: section_positions[0][0]]
        pre_text = _strip_commands(pre_section)
        if pre_text.strip():
            doc.sections.append(
                {
                    "level": 1,
                    "title": doc.title or "",
                    "content": pre_text,
                    "type": "text",
                }
            )

        for i, (pos, level, title) in enumerate(section_positions):
            end_pos = section_positions[i + 1][0] if i + 1 < len(section_positions) else len(content)
            section_raw = content[pos:end_pos]
            section_text = _strip_commands(section_raw)

            has_math = bool(_MATH_ENV_RE.search(section_raw)) or bool(_DISPLAY_MATH_RE.search(section_raw))

            doc.sections.append(
                {
                    "level": level,
                    "title": title,
                    "content": section_text,
                    "type": "math" if has_math else "text",
                }
            )

    doc.sections.extend(math_sections)

    if not doc.title:
        doc.title = Path(file_path).stem

    doc.parse_status = "success"
    return doc
