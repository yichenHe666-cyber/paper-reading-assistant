import logging
import re
from pathlib import Path

from app.config import get_settings
from app.database.session import SessionLocal
from app.models.knowledge_edge import KnowledgeEdge

logger = logging.getLogger(__name__)


def query_for_context(query: str, max_chars: int = None, enhanced: bool = False) -> str:
    settings = get_settings()
    if max_chars is None:
        max_chars = settings.knowledge_enhanced_context_chars if enhanced else settings.knowledge_max_context_chars

    wiki_results = _search_wiki_pages(query, max_chars // 2)
    graph_results = _traverse_knowledge_graph(query, max_chars // 4)
    memory_results = _recall_memories(query, max_chars // 4)

    all_segments = []
    all_segments.extend(wiki_results)
    all_segments.extend(graph_results)
    all_segments.extend(memory_results)

    if not all_segments:
        return ""

    all_segments.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    output_parts = []
    total_chars = 0
    for seg in all_segments:
        text = seg.get("text", "")
        annotation = seg.get("annotation", "")
        entry = f"{text}\n{annotation}" if annotation else text
        if total_chars + len(entry) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 50:
                entry = entry[:remaining] + "..."
                output_parts.append(entry)
            break
        output_parts.append(entry)
        total_chars += len(entry)

    return "\n\n".join(output_parts)


def _search_wiki_pages(query: str, max_chars: int) -> list:
    settings = get_settings()
    wiki_base = Path(settings.knowledge_base_path)
    wiki_dir = wiki_base / "wiki"

    if not wiki_dir.exists():
        return []

    keywords = _extract_keywords(query)
    if not keywords:
        return []

    results = []
    for md_file in wiki_dir.rglob("*.md"):
        if md_file.name in ("log.md",):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        score = _compute_relevance_score(content, keywords)
        if score <= 0:
            continue

        rel_path = str(md_file.relative_to(wiki_dir))
        title = _extract_title(content) or md_file.stem
        snippet = _extract_snippet(content, keywords, max_chars=400)

        confidence = min(score / max(len(keywords), 1), 1.0)
        annotation = f"[Wiki概念|置信度:{confidence:.1f}]"

        results.append({
            "text": f"**{title}** ({rel_path})\n{snippet}",
            "annotation": annotation,
            "score": score,
            "source": "wiki",
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    total = 0
    filtered = []
    for r in results:
        if total + len(r["text"]) > max_chars:
            break
        filtered.append(r)
        total += len(r["text"])

    return filtered


def _traverse_knowledge_graph(query: str, max_chars: int) -> list:
    keywords = _extract_keywords(query)
    if not keywords:
        return []

    db = SessionLocal()
    try:
        all_edges = db.query(KnowledgeEdge).all()
    except Exception as e:
        logger.error(f"查询知识图谱失败: {e}")
        return []
    finally:
        db.close()

    matched_concepts = set()
    for kw in keywords:
        for edge in all_edges:
            if kw.lower() in edge.source_concept.lower() or kw.lower() in edge.target_concept.lower():
                matched_concepts.add(edge.source_concept)
                matched_concepts.add(edge.target_concept)

    if not matched_concepts:
        return []

    related_edges = []
    for edge in all_edges:
        if edge.source_concept in matched_concepts or edge.target_concept in matched_concepts:
            related_edges.append(edge)

    results = []
    seen_pairs = set()
    for edge in related_edges:
        pair = tuple(sorted([edge.source_concept, edge.target_concept]))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        strength = edge.strength or 0.5
        annotation = f"[知识图谱|关系:{edge.relation_type}|强度:{strength:.1f}]"

        text = f"{edge.source_concept} —[{edge.relation_type}]→ {edge.target_concept}"
        if edge.evidence:
            text += f" ({edge.evidence})"

        results.append({
            "text": text,
            "annotation": annotation,
            "score": strength,
            "source": "graph",
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    total = 0
    filtered = []
    for r in results:
        if total + len(r["text"]) > max_chars:
            break
        filtered.append(r)
        total += len(r["text"])

    return filtered


def _recall_memories(query: str, max_chars: int) -> list:
    try:
        from app.services.memory_engine import MemoryEngine
        from app.database.session import SessionLocal as _SL

        me = MemoryEngine()
        db = _SL()
        try:
            memories = me.recall(db, query=query, limit=5)
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"记忆召回失败: {e}")
        return []

    results = []
    for mem in memories:
        if not mem.content:
            continue
        memory_type = getattr(mem, "memory_type", "unknown")
        confidence = getattr(mem, "confidence", 0.5) or 0.5
        annotation = f"[记忆|类型:{memory_type}|置信度:{confidence:.1f}]"

        snippet = mem.content[:300]
        results.append({
            "text": snippet,
            "annotation": annotation,
            "score": float(confidence),
            "source": "memory",
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    total = 0
    filtered = []
    for r in results:
        if total + len(r["text"]) > max_chars:
            break
        filtered.append(r)
        total += len(r["text"])

    return filtered


def _extract_keywords(query: str) -> list:
    stopwords = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
        "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
        "什么", "怎么", "如何", "为什么", "哪", "哪些", "可以", "能",
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can",
        "what", "how", "why", "which", "who", "when", "where",
    }

    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z][a-zA-Z0-9_-]*", query)
    keywords = []
    for token in tokens:
        if token.lower() not in stopwords and len(token) > 1:
            keywords.append(token)
        elif len(token) >= 2 and token.lower() not in stopwords:
            keywords.append(token)

    if not keywords and len(query) > 1:
        keywords = [query]

    return keywords[:10]


def _compute_relevance_score(content: str, keywords: list) -> float:
    content_lower = content.lower()
    score = 0.0
    for kw in keywords:
        kw_lower = kw.lower()
        count = content_lower.count(kw_lower)
        if count > 0:
            title = _extract_title(content)
            if title and kw_lower in title.lower():
                score += 3.0 * min(count, 5)
            else:
                score += 1.0 * min(count, 5)
    return score


def _extract_title(content: str) -> str:
    m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    h1 = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if h1:
        return h1.group(1).strip()
    return ""


def _extract_snippet(content: str, keywords: list, max_chars: int = 400) -> str:
    lines = content.split("\n")
    relevant_lines = []
    for line in lines:
        line_lower = line.lower()
        if any(kw.lower() in line_lower for kw in keywords):
            relevant_lines.append(line.strip())

    if not relevant_lines:
        body_start = 0
        for i, line in enumerate(lines):
            if line.strip() == "---":
                body_start = i + 1
                break
        for i in range(body_start, min(body_start + 10, len(lines))):
            if lines[i].strip() and not lines[i].startswith("#") and not lines[i].startswith("---"):
                relevant_lines.append(lines[i].strip())

    snippet = "\n".join(relevant_lines)
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars] + "..."
    return snippet
