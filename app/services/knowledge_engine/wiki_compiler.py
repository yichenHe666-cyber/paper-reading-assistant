import json
import logging
import re
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.models.knowledge_document import KnowledgeDocument

logger = logging.getLogger(__name__)


def _slug(text: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"\s+", "-", safe).strip("-")[:60]


def _read_file(rel_path: str) -> str:
    settings = get_settings()
    p = Path(settings.knowledge_base_path) / rel_path
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def _write_file(rel_path: str, content: str):
    settings = get_settings()
    p = Path(settings.knowledge_base_path) / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _append_log(entry: str):
    settings = get_settings()
    log_path = Path(settings.knowledge_base_path) / "wiki" / "log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_line = f"\n## [{stamp}] {entry}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(log_line)


def compile_to_wiki(
    document: KnowledgeDocument,
    knowledge: dict,
    edges: list,
) -> dict:
    stats = {"new_pages": 0, "updated_pages": 0, "errors": []}
    today = datetime.now().strftime("%Y-%m-%d")
    doc_title = document.title or "未命名文档"
    doc_slug = _slug(doc_title)
    doc_authors = document.authors or "未知"
    doc_category = document.category or "未分类"

    _compile_source_page(doc_slug, doc_title, doc_authors, doc_category, knowledge, today, stats)

    _compile_concept_pages(knowledge, doc_slug, edges, today, stats)

    _compile_method_pages(knowledge, doc_slug, today, stats)

    _compile_controversy_pages(knowledge, doc_slug, today, stats)

    _update_overview(doc_title, doc_slug, doc_category, knowledge, today, stats)

    _update_index(doc_title, doc_slug, knowledge, stats)

    concept_names = [c.get("name", "") for c in knowledge.get("concepts", [])]
    method_names = [m.get("name", "") for m in knowledge.get("methods", [])]
    _append_log(
        f"COMPILE {doc_title} → "
        f"新建概念 [{', '.join(concept_names[:5])}], "
        f"新建方法 [{', '.join(method_names[:3])}], "
        f"新建 {stats['new_pages']} 页, 更新 {stats['updated_pages']} 页"
    )

    return stats


def _compile_source_page(
    doc_slug: str,
    doc_title: str,
    doc_authors: str,
    doc_category: str,
    knowledge: dict,
    today: str,
    stats: dict,
):
    concepts = knowledge.get("concepts", [])
    methods = knowledge.get("methods", [])
    causal_chains = knowledge.get("causal_chains", [])
    practical_points = knowledge.get("practical_points", [])

    concepts_list = "\n".join(
        f"- [[{c.get('name', '')}]] — {c.get('one_sentence', '')}"
        for c in concepts
    )
    methods_list = "\n".join(
        f"- [[{m.get('name', '')}]] — {m.get('description', '')[:80]}"
        for m in methods
    )
    chains_list = "\n".join(
        f"- {ch.get('cause', '')} → {ch.get('effect', '')}"
        for ch in causal_chains
    )
    points_list = "\n".join(
        f"- {p.get('point', '')}：{p.get('value', '')}"
        for p in practical_points
    )

    md = f"""---
title: "{doc_title}"
type: source
category: {doc_category}
created: {today}
updated: {today}
tags: []
authors: "{doc_authors}"
---

# {doc_title}

## 核心概念
{concepts_list if concepts_list else "无"}

## 方法论
{methods_list if methods_list else "无"}

## 因果链
{chains_list if chains_list else "无"}

## 实践要点
{points_list if points_list else "无"}

---
*由知识引擎编译*
"""
    _write_file(f"wiki/sources/{doc_slug}.md", md)
    stats["new_pages"] += 1


def _compile_concept_pages(
    knowledge: dict,
    doc_slug: str,
    edges: list,
    today: str,
    stats: dict,
):
    concepts = knowledge.get("concepts", [])
    for concept in concepts:
        name = concept.get("name", "")
        if not name:
            continue

        slug = _slug(name)
        concept_path = Path(get_settings().knowledge_base_path) / "wiki" / "concepts" / f"{slug}.md"

        related_section = _build_related_section(name, edges)

        if concept_path.exists():
            try:
                current = concept_path.read_text(encoding="utf-8")
                new_section = f"""

## 来自 [[{doc_slug}]] 的新视角

### 定义补充
{concept.get('definition', '')}

### 一句话理解
> {concept.get('one_sentence', '')}

{related_section}
"""
                current += new_section
                updated_at = f"\nupdated: {today}"
                current = re.sub(r"\nupdated:.*", updated_at, current)

                sources_match = re.search(r"sources:\s*\[(.*?)\]", current)
                if sources_match and doc_slug not in sources_match.group(1):
                    current = current.replace(
                        sources_match.group(0),
                        sources_match.group(0).rstrip("]") + f', "{doc_slug}"]',
                    )

                concept_path.write_text(current, encoding="utf-8")
                stats["updated_pages"] += 1
            except Exception as e:
                stats["errors"].append(f"更新概念页 {name} 失败: {e}")
        else:
            md = f"""---
title: "{name}"
type: concept
category: {concept.get('category', '')}
created: {today}
updated: {today}
tags: []
sources: ["{doc_slug}"]
related_concepts: []
---

# {name}

## 定义
{concept.get('definition', '')}

## 一句话理解
> {concept.get('one_sentence', '')}

## 英文名
{concept.get('name_en', '')}

## 出处
{concept.get('source_location', '')}

{related_section}

---
*由知识引擎编译*
"""
            _write_file(f"wiki/concepts/{slug}.md", md)
            stats["new_pages"] += 1


def _compile_method_pages(
    knowledge: dict,
    doc_slug: str,
    today: str,
    stats: dict,
):
    methods = knowledge.get("methods", [])
    for method in methods:
        name = method.get("name", "")
        if not name:
            continue

        slug = _slug(name)
        steps_text = "\n".join(
            f"{i+1}. {step}" for i, step in enumerate(method.get("steps", []))
        )

        md = f"""---
title: "{name}"
type: method
created: {today}
updated: {today}
tags: []
sources: ["{doc_slug}"]
---

# {name}

## 描述
{method.get('description', '')}

## 步骤
{steps_text if steps_text else "无具体步骤"}

## 适用条件
{method.get('applicable_conditions', '')}

## 出处
{method.get('source_location', '')}

## 来源文档
- [[{doc_slug}]]

---
*由知识引擎编译*
"""
        _write_file(f"wiki/methods/{slug}.md", md)
        stats["new_pages"] += 1


def _compile_controversy_pages(
    knowledge: dict,
    doc_slug: str,
    today: str,
    stats: dict,
):
    controversies = knowledge.get("controversies", [])
    contradiction_edges = [e for e in edges if e.get("relation_type") == "contradicts"]

    all_controversies = list(controversies)
    for edge in contradiction_edges:
        all_controversies.append({
            "topic": f"{edge.get('source_concept', '')} vs {edge.get('target_concept', '')}",
            "viewpoint_a": edge.get("source_concept", ""),
            "viewpoint_b": edge.get("target_concept", ""),
            "evidence": edge.get("evidence", ""),
            "source_location": "知识图谱矛盾检测",
        })

    for cont in all_controversies:
        topic = cont.get("topic", "")
        if not topic:
            continue

        slug = _slug(topic)
        md = f"""---
title: "{topic}"
type: controversy
created: {today}
updated: {today}
tags: [争议]
sources: ["{doc_slug}"]
---

# 争议：{topic}

## 观点 A
{cont.get('viewpoint_a', '')}

## 观点 B
{cont.get('viewpoint_b', '')}

## 现有证据
{cont.get('evidence', '')}

## 出处
{cont.get('source_location', '')}

## 来源文档
- [[{doc_slug}]]

---
*由知识引擎编译*
"""
        _write_file(f"wiki/controversies/{slug}.md", md)
        stats["new_pages"] += 1


def _update_overview(
    doc_title: str,
    doc_slug: str,
    doc_category: str,
    knowledge: dict,
    today: str,
    stats: dict,
):
    overview_path = Path(get_settings().knowledge_base_path) / "wiki" / "overview.md"

    concepts = knowledge.get("concepts", [])
    concept_summary = "\n".join(
        f"- [[{c.get('name', '')}]]：{c.get('one_sentence', '')}"
        for c in concepts[:10]
    )

    new_section = f"""

## {doc_title} ({today})

类别：{doc_category}

### 核心概念
{concept_summary if concept_summary else "无"}

### 来源
- [[{doc_slug}]]

---
"""

    if overview_path.exists():
        try:
            current = overview_path.read_text(encoding="utf-8")
            updated_at = f"\nupdated: {today}"
            if "updated:" in current:
                current = re.sub(r"\nupdated:.*", updated_at, current)
            current += new_section
            overview_path.write_text(current, encoding="utf-8")
            stats["updated_pages"] += 1
        except Exception as e:
            stats["errors"].append(f"更新 overview.md 失败: {e}")
    else:
        md = f"""---
title: "知识库概览"
type: overview
created: {today}
updated: {today}
---

# 知识库概览

{new_section}

---
*由知识引擎编译*
"""
        _write_file("wiki/overview.md", md)
        stats["new_pages"] += 1


def _update_index(
    doc_title: str,
    doc_slug: str,
    knowledge: dict,
    stats: dict,
):
    index_path = Path(get_settings().knowledge_base_path) / "wiki" / "index.md"

    concepts = knowledge.get("concepts", [])
    methods = knowledge.get("methods", [])
    controversies = knowledge.get("controversies", [])

    new_entries = []
    new_entries.append(f"- [{doc_title}](sources/{doc_slug}.md)")
    for c in concepts:
        name = c.get("name", "")
        if name:
            slug = _slug(name)
            new_entries.append(f"- [{name}](concepts/{slug}.md)")
    for m in methods:
        name = m.get("name", "")
        if name:
            slug = _slug(name)
            new_entries.append(f"- [{name}](methods/{slug}.md)")
    for cont in controversies:
        topic = cont.get("topic", "")
        if topic:
            slug = _slug(topic)
            new_entries.append(f"- [{topic}](controversies/{slug}.md)")

    index_addition = "\n" + "\n".join(new_entries) + "\n"

    if index_path.exists():
        try:
            current = index_path.read_text(encoding="utf-8")
            current += index_addition
            index_path.write_text(current, encoding="utf-8")
            stats["updated_pages"] += 1
        except Exception as e:
            stats["errors"].append(f"更新 index.md 失败: {e}")
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        md = f"""---
title: "知识库索引"
type: index
created: {today}
updated: {today}
---

# 知识库索引

## 来源
## 概念
## 方法
## 争议

{index_addition}

---
*由知识引擎编译*
"""
        _write_file("wiki/index.md", md)
        stats["new_pages"] += 1


def _build_related_section(concept_name: str, edges: list) -> str:
    related = []
    for edge in edges:
        source = edge.get("source_concept", "")
        target = edge.get("target_concept", "")
        relation = edge.get("relation_type", "")
        strength = edge.get("strength", 0.5)
        evidence = edge.get("evidence", "")

        if source == concept_name or target == concept_name:
            other = target if source == concept_name else source
            direction = "→" if source == concept_name else "←"
            line = f"- {direction} [[{other}]] ({relation}, 强度: {strength:.1f})"
            if evidence:
                line += f" — {evidence}"
            related.append(line)

    if not related:
        return ""
    return "## 关联概念\n" + "\n".join(related)
