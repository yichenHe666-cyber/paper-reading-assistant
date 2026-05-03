import re
import json
from typing import Optional


SKIP_KEYWORDS = [
    ":open_file_folder:", "Summary of Papers", "full folder", "complete list",
    "download.sh", "Usage", "download utility", "convenience script",
]

SKIP_TOPIC_IDS = {"scripts"}

NON_PAPER_EXTENSIONS = {".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".md", ".txt", ".csv"}


def parse_readme_to_papers(markdown: str, topic_id: str) -> list[dict]:
    if topic_id in SKIP_TOPIC_IDS:
        return []

    ref_links = _parse_reference_links(markdown)
    papers = []
    lines = markdown.split("\n")
    current_paper = None
    current_subtopic = None
    current_community_notes_url = None

    for line in lines:
        stripped = line.strip()

        if re.match(r"^##\s+", stripped):
            potential = re.sub(r"^##\s+", "", stripped).strip()
            if potential not in ("Table of Contents", "Contents", "Contents:", "Included Papers", "External Papers", "QuickCheck", "QuickCheck Testing for Fun and Profit", "Data Cleaning", "Reasoning for the new papers"):
                current_subtopic = potential

        title_match = _extract_paper_link(stripped, ref_links)

        if title_match:
            if current_paper:
                _finalize_paper(current_paper, papers)

            title = title_match["title"].strip()
            link = title_match["link"].strip()

            if any(k.lower() in title.lower() for k in SKIP_KEYWORDS):
                current_paper = None
                current_community_notes_url = None
                continue

            if _is_non_paper_link(link, title):
                current_paper = None
                current_community_notes_url = None
                continue

            paper_id = _make_id(topic_id, title)

            pdf_url = link
            if not link.startswith("http"):
                pdf_url = f"https://github.com/papers-we-love/papers-we-love/blob/master/{topic_id}/{link}"

            current_paper = {
                "id": paper_id,
                "title": title,
                "authors": None,
                "year": None,
                "topic_id": topic_id,
                "subtopic": current_subtopic,
                "pdf_url": pdf_url,
                "community_notes_url": current_community_notes_url,
                "abstract": None,
            }
            current_community_notes_url = None

            _extract_inline_metadata(stripped, current_paper, line_after_link=title_match.get("after_link", ""))

            continue

        if current_paper:
            author_match = re.match(r"^\*\s*\*Authors?\*?\*?\s*:\s*(.+)", stripped)
            if author_match:
                authors_str = author_match.group(1).strip()
                authors_list = [a.strip() for a in re.split(r"[,;&]|\band\b", authors_str) if a.strip()]
                current_paper["authors"] = json.dumps(authors_list, ensure_ascii=False)
                continue

            year_match = re.match(r"^\*\s*\*Year\*?\*?\s*:\s*(\d{4})", stripped)
            if year_match:
                current_paper["year"] = int(year_match.group(1))
                continue

            by_match = re.search(r"\bby\s+(.+)$", stripped)
            if by_match and not current_paper.get("authors"):
                authors_str = by_match.group(1).strip()
                authors_str = re.sub(r"\s+and\s+", ", ", authors_str)
                authors_list = [a.strip().rstrip(".") for a in re.split(r"[,;]", authors_str) if a.strip()]
                if len(authors_list) <= 5:
                    current_paper["authors"] = json.dumps(authors_list, ensure_ascii=False)

            year_inline = re.search(r"\b(1[89]\d{2}|20[0-2]\d)\b", stripped)
            if year_inline and not current_paper.get("year"):
                current_paper["year"] = int(year_inline.group(1))

            notes_match = re.search(r"\[(?:notes|community notes|💬)\]\(([^)]+)\)", stripped, re.IGNORECASE)
            if notes_match:
                current_paper["community_notes_url"] = notes_match.group(1)

        if not title_match:
            notes_link = re.search(r"\[(?:notes|community notes|💬)\]\(([^)]+)\)", stripped, re.IGNORECASE)
            if notes_link and not current_paper:
                current_community_notes_url = notes_link.group(1)

    if current_paper:
        _finalize_paper(current_paper, papers)

    seen_ids = set()
    deduped = []
    for p in papers:
        if p["id"] not in seen_ids:
            seen_ids.add(p["id"])
            deduped.append(p)
    return deduped


def _parse_reference_links(markdown: str) -> dict:
    ref_links = {}
    for m in re.finditer(r"^\[([^\]]+)\]:\s*(.+)$", markdown, re.MULTILINE):
        key = m.group(1).strip()
        url = m.group(2).strip()
        ref_links[key] = url
    return ref_links


def _extract_paper_link(stripped: str, ref_links: dict) -> Optional[dict]:
    m = re.match(r"^###\s*\[([^\]]+)\]\(([^)]+)\)", stripped)
    if m:
        return {"title": m.group(1), "link": m.group(2), "after_link": stripped[m.end():]}

    m = re.match(r"^##\s*\[([^\]]+)\]\(([^)]+)\)", stripped)
    if m:
        return {"title": m.group(1), "link": m.group(2), "after_link": stripped[m.end():]}

    m = re.match(r"^[-*]\s+(?:\:[\w-]+\:\s+)?\[([^\]]+)\]\(([^)]+)\)", stripped)
    if m:
        after = stripped[m.end():]
        return {"title": m.group(1), "link": m.group(2), "after_link": after}

    m = re.match(r"^[-*]\s+(?:\:[\w-]+\:\s+)?\[([^\]]+)\]", stripped)
    if m:
        ref_key = m.group(1).strip()
        if ref_key in ref_links:
            after = stripped[m.end():]
            return {"title": ref_key, "link": ref_links[ref_key], "after_link": after}

    m = re.match(r"^\[([^\]]+)\]\(([^)]+)\)", stripped)
    if m:
        after = stripped[m.end():]
        return {"title": m.group(1), "link": m.group(2), "after_link": after}

    if stripped.startswith("*") or stripped.startswith("-"):
        all_matches = list(re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", stripped))
        if all_matches:
            for match in all_matches:
                title = match.group(1).strip()
                if not _is_emoji_shortcode(title) and not _is_navigation_link(title):
                    after = stripped[match.end():]
                    return {"title": title, "link": match.group(2), "after_link": after}

    return None


def _is_navigation_link(title: str) -> bool:
    nav_keywords = ["sciencedirect", "acm", "doi", "arxiv", "springer", "ieee", "pdf"]
    title_lower = title.lower()
    return any(k == title_lower for k in nav_keywords)


def _is_non_paper_link(link: str, title: str) -> bool:
    if not link.startswith("http") and not link.endswith(".pdf"):
        if not any(link.endswith(ext) for ext in [".ps", ".ps.gz", ".djvu"]):
            return True

    link_lower = link.lower()
    for ext in NON_PAPER_EXTENSIONS:
        if link_lower.endswith(ext):
            return True

    if link.startswith("http") and "github.com" in link and "/blob/" in link:
        path_lower = link.lower()
        for ext in NON_PAPER_EXTENSIONS:
            if path_lower.endswith(ext):
                return True

    return False


def _extract_inline_metadata(stripped: str, paper: dict, line_after_link: str = ""):
    by_match = re.search(r"\bby\s+(.+)$", stripped)
    if by_match:
        authors_str = by_match.group(1).strip()
        year_m = re.search(r"\s*\((\d{4})\)\s*$", authors_str)
        if year_m and not paper.get("year"):
            paper["year"] = int(year_m.group(1))
            authors_str = authors_str[:year_m.start()].strip()
        authors_str = re.sub(r"\s+and\s+", ", ", authors_str)
        authors_list = [a.strip().rstrip(".") for a in re.split(r"[,;]", authors_str) if a.strip()]
        if len(authors_list) <= 5:
            paper["authors"] = json.dumps(authors_list, ensure_ascii=False)

    year_inline = re.search(r"\b(1[89]\d{2}|20[0-2]\d)\b", stripped)
    if year_inline and not paper.get("year"):
        paper["year"] = int(year_inline.group(1))


def _finalize_paper(paper: dict, papers: list):
    if not paper.get("authors"):
        paper["authors"] = json.dumps(["Unknown"])
    papers.append(paper)


def _make_id(topic_id: str, title: str) -> str:
    import hashlib
    safe = re.sub(r"[^\w\s-]", "", title.lower())
    safe = re.sub(r"\s+", "_", safe).strip("_")
    if len(safe) > 60:
        safe = safe[:60]
    hash_suffix = hashlib.md5(title.encode()).hexdigest()[:6]
    return f"{topic_id}/{safe}_{hash_suffix}"


def _is_emoji_shortcode(text: str) -> bool:
    return bool(re.match(r"^:\w+:$", text.strip()))
