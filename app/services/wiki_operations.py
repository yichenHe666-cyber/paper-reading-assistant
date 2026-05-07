import json
import re
from pathlib import Path
from datetime import datetime

try:
    from app.services.llm_navigator import _call_llm
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False

from app.database.session import SessionLocal
from app.models.knowledge_edge import KnowledgeEdge


WIKI_BASE = Path(r"C:\Users\Public\Documents\wiki-knowledge")


def _call_llm_safe(messages, max_tokens=2000):
    if not LLM_AVAILABLE:
        raise RuntimeError("LLM 服务不可用，请检查 LLM_API_KEY 配置")
    return _call_llm(messages, max_tokens)


def _read_file(rel_path: str) -> str:
    p = WIKI_BASE / rel_path
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def _write_file(rel_path: str, content: str):
    p = WIKI_BASE / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _slug(text: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"\s+", "-", safe).strip("-")[:60]


def _append_log(entry: str):
    log_path = WIKI_BASE / "wiki" / "log.md"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_line = f"\n## [{stamp}] {entry}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(log_line)


def _scan_wiki_entries(section: str) -> dict:
    index_md = _read_file("wiki/index.md")
    entries = {}
    in_section = False
    for line in index_md.split("\n"):
        if line.startswith("## ") and section in line:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            m = re.match(r"- \[([^\]]+)\]\(([^)]+)\)", line.strip())
            if m:
                entries[m.group(1)] = m.group(2)
    return entries


def ingest_document(document: dict) -> dict:
    doc_title = document.get("title", "Untitled")
    doc_authors = document.get("authors", "Unknown")
    doc_year = document.get("year", "")
    doc_topic = document.get("topic", document.get("topic_id", document.get("category", "")))
    doc_content = document.get("content", document.get("abstract", "无摘要"))
    doc_id = document.get("id", "")
    doc_format = document.get("file_format", "paper")

    format_labels = {
        "paper": "论文",
        "pdf": "PDF 文档",
        "book": "书籍",
        "report": "报告",
        "thesis": "学位论文",
        "article": "文章",
        "manual": "手册",
        "specification": "规范",
        "standard": "标准",
    }
    doc_type_label = format_labels.get(doc_format, "文档")

    schema = _read_file("schema/AGENTS.md")
    index_md = _read_file("wiki/index.md")

    existing_concepts = {}
    concepts_dir = WIKI_BASE / "wiki" / "concepts"
    if concepts_dir.exists():
        for f in concepts_dir.glob("*.md"):
            existing_concepts[f.stem] = f.read_text(encoding="utf-8")[:500]

    existing_sources = {}
    sources_dir = WIKI_BASE / "wiki" / "sources"
    if sources_dir.exists():
        for f in sources_dir.glob("*.md"):
            existing_sources[f.stem] = f.read_text(encoding="utf-8")[:500]

    prompt = f"""你是 LLM Wiki 维护 AI。

## Schema（操作规则）
{schema[:3000]}

## 当前 Wiki 索引
{index_md[:2000]}

## 已有概念
{json.dumps(list(existing_concepts.keys()), ensure_ascii=False)}

## 已有来源
{json.dumps(list(existing_sources.keys()), ensure_ascii=False)}

## 新{doc_type_label}
标题：{doc_title}
作者：{doc_authors}
年份：{doc_year}
主题/类别：{doc_topic}
内容摘要：{doc_content}
文档类型：{doc_type_label}（{doc_format}）

请以 JSON 返回结构化变更集（只返回 JSON，不要代码块）：

{{
  "source_summary": {{
    "slug": "来源 slug",
    "title": "{doc_title}",
    "one_liner": "一句话概括本{doc_type_label}贡献",
    "key_contributions": ["贡献1", "贡献2", "贡献3"],
    "content_md": "完整的来源摘要 Markdown（含 frontmatter）"
  }},
  "new_concepts": [
    {{
      "slug": "概念-slug",
      "title": "概念名",
      "category": "所属类别",
      "definition": "定义（2-3句）",
      "one_sentence": "一句话理解",
      "content_md": "完整概念页面 Markdown（含 frontmatter）"
    }}
  ],
  "updated_concepts": [
    {{
      "slug": "已有概念-slug",
      "update_type": "strengthen|contradict|extend",
      "new_section": "要追加的 Markdown 内容"
    }}
  ],
  "new_comparisons": [
    {{
      "slug": "对比-slug",
      "title": "A vs B",
      "content_md": "完整对比 Markdown"
    }}
  ],
  "index_updates": "要追加到 index.md 的内容（新增条目的列表行）",
  "log_entry": "INGEST {doc_title} → 新建 [概念列表]，更新 [概念列表]"
}}

规则：
- 优先复用已有概念，避免重复创建
- 如果{doc_type_label}加强了已有概念的理解，写入 updated_concepts
- 每个概念页面必须用 [[wikilink]] 链接到本{doc_type_label}的来源摘要
- 根据{doc_type_label}类型调整提取重点：论文侧重研究贡献，书籍侧重知识体系，报告侧重发现与建议，手册侧重操作流程
- 中文输出，面向大一学生
"""
    messages = [{"role": "user", "content": prompt}]
    content, usage = _call_llm_safe(messages, max_tokens=4000)

    try:
        changes = json.loads(content)
    except json.JSONDecodeError:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])
        changes = json.loads(content)

    executed = {"new_pages": 0, "updated_pages": 0, "errors": []}

    source_summary = changes.get("source_summary", {})
    if source_summary:
        slug = source_summary.get("slug", _slug(doc_title))
        md = source_summary.get("content_md", "")
        if md:
            _write_file(f"wiki/sources/{slug}.md", md)
            executed["new_pages"] += 1

    for c in changes.get("new_concepts", []):
        slug = c.get("slug", _slug(c.get("title", "")))
        if slug and slug not in existing_concepts:
            md = c.get("content_md", "")
            if not md:
                today = datetime.now().strftime("%Y-%m-%d")
                md = f"""---
title: "{c.get('title', '')}"
type: concept
category: {c.get('category', '')}
created: {today}
updated: {today}
tags: []
sources: ["{source_summary.get('slug', '')}"]
related_concepts: []
---

# {c.get('title', '')}

## 定义
{c.get('definition', '')}

## 一句话理解
> {c.get('one_sentence', '')}

## 关联来源
- [[{source_summary.get('slug', '')}]]

---
*由 LLM Wiki 引擎生成*
"""
            _write_file(f"wiki/concepts/{slug}.md", md)
            executed["new_pages"] += 1

    for uc in changes.get("updated_concepts", []):
        slug = uc.get("slug", "")
        section = uc.get("new_section", "")
        if slug and section:
            existing_path = WIKI_BASE / "wiki" / "concepts" / f"{slug}.md"
            if existing_path.exists():
                current = existing_path.read_text(encoding="utf-8")
                updated_at = f"\nupdated: {datetime.now().strftime('%Y-%m-%d')}"
                current = re.sub(r"\nupdated:.*", updated_at, current)
                current += f"\n\n{section}\n"
                existing_path.write_text(current, encoding="utf-8")
                executed["updated_pages"] += 1
            else:
                executed["errors"].append(f"概念 {slug} 不存在，无法更新")

    for comp in changes.get("new_comparisons", []):
        slug = comp.get("slug", "")
        md = comp.get("content_md", "")
        if slug and md:
            _write_file(f"wiki/comparisons/{slug}.md", md)
            executed["new_pages"] += 1

    index_updates = changes.get("index_updates", "")
    if index_updates:
        current_index = _read_file("wiki/index.md")
        today = datetime.now().strftime("%Y-%m-%d")
        current_index = current_index.replace("updated: ", f"updated: {today}")
        current_index += f"\n{index_updates}\n"
        _write_file("wiki/index.md", current_index)

    log_entry = changes.get("log_entry", f"INGEST {doc_title}")
    _append_log(log_entry)

    return {
        "status": "ok",
        "executed": executed,
        "log_entry": log_entry,
        "usage": usage,
    }


ingest_paper = ingest_document


def _query_edges_for_concepts(concept_slugs: list) -> list:
    if not concept_slugs:
        return []
    try:
        db = SessionLocal()
        edges = (
            db.query(KnowledgeEdge)
            .filter(
                (KnowledgeEdge.source_concept.in_(concept_slugs))
                | (KnowledgeEdge.target_concept.in_(concept_slugs))
            )
            .all()
        )
        result = []
        for e in edges:
            result.append({
                "source": e.source_concept,
                "target": e.target_concept,
                "relation": e.relation_type,
                "strength": e.strength,
                "evidence": e.evidence,
            })
        db.close()
        return result
    except Exception:
        return []


def _get_all_edge_concepts() -> dict:
    try:
        db = SessionLocal()
        edges = db.query(KnowledgeEdge).all()
        concept_edges = {}
        for e in edges:
            for concept in (e.source_concept, e.target_concept):
                if concept not in concept_edges:
                    concept_edges[concept] = {"outgoing": [], "incoming": []}
            concept_edges[e.source_concept]["outgoing"].append({
                "target": e.target_concept,
                "relation": e.relation_type,
                "strength": e.strength,
            })
            concept_edges[e.target_concept]["incoming"].append({
                "source": e.source_concept,
                "relation": e.relation_type,
                "strength": e.strength,
            })
        db.close()
        return concept_edges
    except Exception:
        return {}


def ingest_knowledge(document: dict, knowledge: dict, edges: list) -> dict:
    doc_title = document.get("title", "Untitled")
    doc_authors = document.get("authors", "Unknown")
    doc_year = document.get("year", "")
    doc_topic = document.get("topic", document.get("topic_id", document.get("category", "")))
    doc_id = document.get("id", "")
    doc_format = document.get("file_format", "paper")
    source_slug = _slug(doc_title)

    stats = {"new_pages": 0, "updated_pages": 0, "edges_written": 0, "errors": []}
    today = datetime.now().strftime("%Y-%m-%d")

    source_md = f"""---
title: "{doc_title}"
type: source
category: {doc_topic}
format: {doc_format}
created: {today}
updated: {today}
tags: []
authors: "{doc_authors}"
year: "{doc_year}"
---

# {doc_title}

## 概述
{knowledge.get("summary", "")}

## 关键贡献
"""
    for contrib in knowledge.get("key_contributions", []):
        source_md += f"- {contrib}\n"

    concepts = knowledge.get("concepts", [])
    if concepts:
        source_md += "\n## 提取的概念\n"
        for c in concepts:
            cslug = _slug(c.get("name", c.get("title", "")))
            source_md += f"- [[{cslug}]] — {c.get('definition', c.get('one_sentence', ''))}\n"

    methods = knowledge.get("methods", [])
    if methods:
        source_md += "\n## 提取的方法\n"
        for m in methods:
            mslug = _slug(m.get("name", m.get("title", "")))
            source_md += f"- [[{mslug}]] — {m.get('description', m.get('one_sentence', ''))}\n"

    _write_file(f"wiki/sources/{source_slug}.md", source_md)
    stats["new_pages"] += 1

    existing_concepts = set()
    concepts_dir = WIKI_BASE / "wiki" / "concepts"
    if concepts_dir.exists():
        for f in concepts_dir.glob("*.md"):
            existing_concepts.add(f.stem)

    for c in concepts:
        cslug = _slug(c.get("name", c.get("title", "")))
        if not cslug:
            continue
        concept_title = c.get("name", c.get("title", ""))
        concept_md = f"""---
title: "{concept_title}"
type: concept
category: {c.get('category', doc_topic)}
created: {today}
updated: {today}
tags: {json.dumps(c.get('tags', []), ensure_ascii=False)}
sources: ["{source_slug}"]
related_concepts: []
---

# {concept_title}

## 定义
{c.get('definition', '')}

## 一句话理解
> {c.get('one_sentence', '')}

## 关联来源
- [[{source_slug}]]

---
*由 LLM Wiki 知识引擎生成*
"""
        concept_path = WIKI_BASE / "wiki" / "concepts" / f"{cslug}.md"
        if concept_path.exists():
            current = concept_path.read_text(encoding="utf-8")
            updated_at_line = f"\nupdated: {today}"
            current = re.sub(r"\nupdated:.*", updated_at_line, current)
            new_section = f"\n\n## 来自 {doc_title} 的补充\n{c.get('definition', '')}\n\n> {c.get('one_sentence', '')}\n\n- [[{source_slug}]]\n"
            current += new_section
            concept_path.write_text(current, encoding="utf-8")
            stats["updated_pages"] += 1
        else:
            _write_file(f"wiki/concepts/{cslug}.md", concept_md)
            stats["new_pages"] += 1

    for m in methods:
        mslug = _slug(m.get("name", m.get("title", "")))
        if not mslug:
            continue
        method_title = m.get("name", m.get("title", ""))
        method_md = f"""---
title: "{method_title}"
type: method
category: {m.get('category', doc_topic)}
created: {today}
updated: {today}
tags: {json.dumps(m.get('tags', []), ensure_ascii=False)}
sources: ["{source_slug}"]
---

# {method_title}

## 描述
{m.get('description', m.get('one_sentence', ''))}

## 适用场景
{m.get('applicability', '')}

## 步骤
"""
        steps = m.get("steps", [])
        if steps:
            for i, step in enumerate(steps, 1):
                method_md += f"{i}. {step}\n"
        else:
            method_md += "（待补充）\n"

        method_md += f"""
## 关联来源
- [[{source_slug}]]

## 关联概念
"""
        related = m.get("related_concepts", [])
        for rc in related:
            rcslug = _slug(rc)
            method_md += f"- [[{rcslug}]]\n"

        method_md += "\n---\n*由 LLM Wiki 知识引擎生成*\n"
        _write_file(f"wiki/methods/{mslug}.md", method_md)
        stats["new_pages"] += 1

    for cv in knowledge.get("controversies", []):
        cvslug = _slug(cv.get("title", cv.get("name", "")))
        if not cvslug:
            continue
        cv_title = cv.get("title", cv.get("name", ""))
        cv_md = f"""---
title: "{cv_title}"
type: controversy
category: {cv.get('category', doc_topic)}
created: {today}
updated: {today}
tags: {json.dumps(cv.get('tags', []), ensure_ascii=False)}
sources: ["{source_slug}"]
status: open
---

# {cv_title}

## 争议描述
{cv.get('description', '')}

## 不同观点
"""
        viewpoints = cv.get("viewpoints", cv.get("positions", []))
        for vp in viewpoints:
            vp_title = vp.get("title", vp.get("position", ""))
            vp_desc = vp.get("description", vp.get("evidence", ""))
            cv_md += f"### {vp_title}\n{vp_desc}\n\n"

        cv_md += f"""## 关联来源
- [[{source_slug}]]

---
*由 LLM Wiki 知识引擎生成*
"""
        _write_file(f"wiki/controversies/{cvslug}.md", cv_md)
        stats["new_pages"] += 1

    if edges:
        try:
            db = SessionLocal()
            for edge in edges:
                db_edge = KnowledgeEdge(
                    source_concept=edge.get("source", ""),
                    target_concept=edge.get("target", ""),
                    relation_type=edge.get("relation", "related_to"),
                    strength=edge.get("strength", 0.5),
                    evidence=edge.get("evidence", ""),
                    source_document_id=int(doc_id) if doc_id and str(doc_id).isdigit() else None,
                    is_verified=False,
                )
                db.add(db_edge)
            db.commit()
            stats["edges_written"] = len(edges)
            db.close()
        except Exception as e:
            stats["errors"].append(f"写入知识边失败: {str(e)}")

    overview_path = WIKI_BASE / "wiki" / "overview.md"
    if overview_path.exists():
        overview = overview_path.read_text(encoding="utf-8")
    else:
        overview = f"---\ntitle: Wiki 概览\ncreated: {today}\nupdated: {today}\n---\n\n# Wiki 概览\n"
    overview += f"\n## {today} — {doc_title}\n"
    if concepts:
        overview += "### 新增/更新概念\n"
        for c in concepts:
            cslug = _slug(c.get("name", c.get("title", "")))
            overview += f"- [[{cslug}]]\n"
    if methods:
        overview += "### 新增方法\n"
        for m in methods:
            mslug = _slug(m.get("name", m.get("title", "")))
            overview += f"- [[{mslug}]]\n"
    if knowledge.get("controversies"):
        overview += "### 新增争议\n"
        for cv in knowledge.get("controversies", []):
            cvslug = _slug(cv.get("title", cv.get("name", "")))
            overview += f"- [[{cvslug}]]\n"
    _write_file("wiki/overview.md", overview)

    index_md = _read_file("wiki/index.md")
    index_updates = f"\n### {today} — {doc_title}\n"
    index_updates += f"- [来源: {doc_title}](sources/{source_slug}.md)\n"
    for c in concepts:
        cslug = _slug(c.get("name", c.get("title", "")))
        index_updates += f"- [概念: {c.get('name', c.get('title', ''))}](concepts/{cslug}.md)\n"
    for m in methods:
        mslug = _slug(m.get("name", m.get("title", "")))
        index_updates += f"- [方法: {m.get('name', m.get('title', ''))}](methods/{mslug}.md)\n"
    for cv in knowledge.get("controversies", []):
        cvslug = _slug(cv.get("title", cv.get("name", "")))
        index_updates += f"- [争议: {cv.get('title', cv.get('name', ''))}](controversies/{cvslug}.md)\n"
    index_md += index_updates
    _write_file("wiki/index.md", index_md)

    concept_names = [_slug(c.get("name", c.get("title", ""))) for c in concepts]
    method_names = [_slug(m.get("name", m.get("title", ""))) for m in methods]
    controversy_names = [_slug(cv.get("title", cv.get("name", ""))) for cv in knowledge.get("controversies", [])]
    log_parts = [f"INGEST_KNOWLEDGE {doc_title}"]
    if concept_names:
        log_parts.append(f"概念[{len(concept_names)}]: {', '.join(concept_names[:5])}")
    if method_names:
        log_parts.append(f"方法[{len(method_names)}]: {', '.join(method_names[:5])}")
    if controversy_names:
        log_parts.append(f"争议[{len(controversy_names)}]: {', '.join(controversy_names[:5])}")
    if edges:
        log_parts.append(f"边[{len(edges)}]")
    _append_log(" | ".join(log_parts))

    return {
        "status": "ok",
        "source_slug": source_slug,
        "stats": stats,
    }


def query_wiki(question: str) -> dict:
    index_md = _read_file("wiki/index.md")
    schema = _read_file("schema/AGENTS.md")[:1000]

    all_pages = {}
    concept_slugs = []
    for md_file in (WIKI_BASE / "wiki").rglob("*.md"):
        rel = str(md_file.relative_to(WIKI_BASE / "wiki"))
        if rel in ("index.md", "log.md"):
            continue
        all_pages[rel] = md_file.read_text(encoding="utf-8")[:1000]
        if rel.startswith("concepts/"):
            concept_slugs.append(rel.replace("concepts/", "").replace(".md", ""))

    graph_edges = _query_edges_for_concepts(concept_slugs)

    graph_context = ""
    related_concepts_note = ""
    if graph_edges:
        edge_descriptions = []
        for e in graph_edges:
            edge_descriptions.append(
                f"{e['source']} —[{e['relation']}]→ {e['target']} (强度: {e['strength']})"
            )
        graph_context = f"\n## 知识图谱关系\n" + "\n".join(edge_descriptions[:50])

        related_concepts = set()
        for e in graph_edges:
            related_concepts.add(e["source"])
            related_concepts.add(e["target"])
        if related_concepts:
            related_concepts_note = f"\n注意：以下概念在知识图谱中有关联关系：{', '.join(sorted(related_concepts)[:20])}。请在回答中适当提及相关概念及其关系。"

    prompt = f"""你是 LLM Wiki 查询 AI。

## Wiki 索引
{index_md[:2000]}

## 可用页面
{json.dumps(list(all_pages.keys()), ensure_ascii=False)}
{graph_context}
{related_concepts_note}

## 用户问题
{question}

请综合 wiki 内容和知识图谱关系回答（中文），以 JSON 返回：

{{
  "answer": "你的回答（Markdown 格式，带 [[wiki-links]] 引用）",
  "sources_used": ["引用的页面路径"],
  "related_concepts": ["回答中涉及的概念及其图谱关系"],
  "confidence": "high|medium|low",
  "save_as_query": true/false,
  "query_title": "如果 save_as_query=true，建议的标题",
  "query_content_md": "如果 save_as_query=true，完整的问答页面 Markdown（含 frontmatter）"
}}

规则：
- 回答面向大一学生，亲切易懂
- 引用时用 [[wiki/页面路径]] 格式
- 如果问题涉及的概念在知识图谱中有关系，请在回答中说明这些关系
- 如果问题无法从 wiki 回答，诚实说明
"""
    messages = [{"role": "user", "content": prompt}]
    content, usage = _call_llm_safe(messages, max_tokens=2500)

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])
        result = json.loads(content)

    if result.get("save_as_query") and result.get("query_content_md"):
        title = result.get("query_title", "query")
        slug = _slug(title)
        _write_file(f"wiki/queries/{slug}.md", result["query_content_md"])

        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        _append_log(f"QUERY [{question[:40]}] → 保存答案: {title}")

    return {"status": "ok", "result": result, "graph_edges_used": len(graph_edges), "usage": usage}


def lint_wiki() -> dict:
    schema = _read_file("schema/AGENTS.md")
    index_md = _read_file("wiki/index.md")

    all_pages = {}
    concept_slugs = []
    for md_file in (WIKI_BASE / "wiki").rglob("*.md"):
        rel = str(md_file.relative_to(WIKI_BASE / "wiki"))
        if rel in ("index.md", "log.md"):
            continue
        all_pages[rel] = md_file.read_text(encoding="utf-8")[:800]
        if rel.startswith("concepts/"):
            concept_slugs.append(rel.replace("concepts/", "").replace(".md", ""))

    concept_edges = _get_all_edge_concepts()

    orphan_concepts = []
    broken_chains = []

    for slug in concept_slugs:
        if slug not in concept_edges:
            orphan_concepts.append(slug)
        else:
            edge_info = concept_edges[slug]
            has_outgoing = len(edge_info["outgoing"]) > 0
            has_incoming = len(edge_info["incoming"]) > 0
            if has_outgoing and not has_incoming:
                broken_chains.append({
                    "concept": slug,
                    "direction": "outgoing_only",
                    "targets": [e["target"] for e in edge_info["outgoing"]],
                })
            elif has_incoming and not has_outgoing:
                broken_chains.append({
                    "concept": slug,
                    "direction": "incoming_only",
                    "sources": [e["source"] for e in edge_info["incoming"]],
                })

    graph_health_context = ""
    if orphan_concepts:
        graph_health_context += f"\n### 孤立概念（无知识图谱边）\n"
        for oc in orphan_concepts:
            graph_health_context += f"- {oc}\n"
    if broken_chains:
        graph_health_context += f"\n### 断链概念（仅有单向关系）\n"
        for bc in broken_chains:
            direction = "仅出边" if bc["direction"] == "outgoing_only" else "仅入边"
            if bc["direction"] == "outgoing_only":
                targets = ", ".join(bc["targets"][:5])
                graph_health_context += f"- {bc['concept']}（{direction}→ {targets}）\n"
            else:
                sources = ", ".join(bc["sources"][:5])
                graph_health_context += f"- {bc['concept']}（{direction}← {sources}）\n"

    prompt = f"""你是 LLM Wiki 健康检查 AI。

## Schema
{schema[:2000]}

## Wiki 索引
{index_md[:1500]}

## 所有页面内容
{json.dumps({k: v[:400] for k, v in all_pages.items()}, ensure_ascii=False)}

## 知识图谱健康状态
{graph_health_context if graph_health_context else "知识图谱为空或不可用"}

请对 wiki 做全面健康检查，以 JSON 返回：

{{
  "score": "A / B / C / D",
  "issues": [
    {{
      "severity": "high|medium|low",
      "page": "受影响的页面路径",
      "description": "问题描述",
      "suggestion": "修复建议"
    }}
  ],
  "stats": {{
    "total_pages": N,
    "sources": N,
    "concepts": N,
    "methods": N,
    "controversies": N,
    "comparisons": N,
    "synthesis": N,
    "queries": N,
    "orphan_concepts": N,
    "broken_chains": N,
    "missing_cross_references": N
  }},
  "graph_health": {{
    "total_edges": N,
    "orphan_concepts": ["无边的概念列表"],
    "broken_chains": ["单向关系概念列表"],
    "suggestions": ["图谱修复建议"]
  }},
  "lint_report_md": "完整的检查报告 Markdown（含 frontmatter）"
}}

检查项：
1. 矛盾声明（两个页面说不同的事情）
2. 孤立概念（没有页面引用它，也没有知识图谱边）
3. 缺失概念页（index 提到但没有对应文件）
4. 缺失交叉引用（有概念但页面间没有 [[链接]]）
5. 过期声明
6. 数据缺口
7. 知识图谱孤立节点（概念没有任何边连接）
8. 知识图谱断链（概念仅有单向关系，缺少反向关系）
"""
    messages = [{"role": "user", "content": prompt}]
    content, usage = _call_llm_safe(messages, max_tokens=3000)

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])
        result = json.loads(content)

    if "graph_health" not in result:
        result["graph_health"] = {
            "total_edges": len(concept_edges),
            "orphan_concepts": orphan_concepts,
            "broken_chains": [bc["concept"] for bc in broken_chains],
            "suggestions": [],
        }

    report_md = result.get("lint_report_md", "")
    if report_md:
        _write_file("wiki/lint-report.md", report_md)

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    issues_count = len(result.get("issues", []))
    _append_log(f"LINT → 得分: {result.get('score', 'N/A')}, 发现 {issues_count} 个问题, 孤立概念 {len(orphan_concepts)}, 断链 {len(broken_chains)}")

    return {
        "status": "ok",
        "result": result,
        "graph_summary": {
            "orphan_concepts_count": len(orphan_concepts),
            "broken_chains_count": len(broken_chains),
        },
        "usage": usage,
    }
