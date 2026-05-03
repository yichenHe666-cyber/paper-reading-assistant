import json
import re
from pathlib import Path
from datetime import datetime

try:
    from app.services.llm_navigator import _call_llm
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False


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


def ingest_paper(paper: dict) -> dict:
    paper_title = paper.get("title", "Untitled")
    paper_authors = paper.get("authors", "Unknown")
    paper_year = paper.get("year", "")
    paper_topic = paper.get("topic_id", "")
    paper_abstract = paper.get("abstract", "无摘要")
    paper_id = paper.get("id", "")

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

## 新论文
标题：{paper_title}
作者：{paper_authors}
年份：{paper_year}
主题：{paper_topic}
摘要：{paper_abstract}

请以 JSON 返回结构化变更集（只返回 JSON，不要代码块）：

{{
  "source_summary": {{
    "slug": "来源 slug",
    "title": "{paper_title}",
    "one_liner": "一句话概括本文贡献",
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
  "log_entry": "INGEST {paper_title} → 新建 [概念列表]，更新 [概念列表]"
}}

规则：
- 优先复用已有概念，避免重复创建
- 如果论文加强了已有概念的理解，写入 updated_concepts
- 每个概念页面必须用 [[wikilink]] 链接到本论文的来源摘要
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
        slug = source_summary.get("slug", _slug(paper_title))
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

## 关联论文
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

    log_entry = changes.get("log_entry", f"INGEST {paper_title}")
    _append_log(log_entry)

    return {
        "status": "ok",
        "executed": executed,
        "log_entry": log_entry,
        "usage": usage,
    }


def query_wiki(question: str) -> dict:
    index_md = _read_file("wiki/index.md")
    schema = _read_file("schema/AGENTS.md")[:1000]

    all_pages = {}
    for md_file in (WIKI_BASE / "wiki").rglob("*.md"):
        rel = str(md_file.relative_to(WIKI_BASE / "wiki"))
        if rel in ("index.md", "log.md"):
            continue
        all_pages[rel] = md_file.read_text(encoding="utf-8")[:1000]

    prompt = f"""你是 LLM Wiki 查询 AI。

## Wiki 索引
{index_md[:2000]}

## 可用页面
{json.dumps(list(all_pages.keys()), ensure_ascii=False)}

## 用户问题
{question}

请综合 wiki 内容回答（中文），以 JSON 返回：

{{
  "answer": "你的回答（Markdown 格式，带 [[wiki-links]] 引用）",
  "sources_used": ["引用的页面路径"],
  "confidence": "high|medium|low",
  "save_as_query": true/false,
  "query_title": "如果 save_as_query=true，建议的标题",
  "query_content_md": "如果 save_as_query=true，完整的问答页面 Markdown（含 frontmatter）"
}}

规则：
- 回答面向大一学生，亲切易懂
- 引用时用 [[wiki/页面路径]] 格式
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

    return {"status": "ok", "result": result, "usage": usage}


def lint_wiki() -> dict:
    schema = _read_file("schema/AGENTS.md")
    index_md = _read_file("wiki/index.md")

    all_pages = {}
    for md_file in (WIKI_BASE / "wiki").rglob("*.md"):
        rel = str(md_file.relative_to(WIKI_BASE / "wiki"))
        if rel in ("index.md", "log.md"):
            continue
        all_pages[rel] = md_file.read_text(encoding="utf-8")[:800]

    prompt = f"""你是 LLM Wiki 健康检查 AI。

## Schema
{schema[:2000]}

## Wiki 索引
{index_md[:1500]}

## 所有页面内容
{json.dumps({k: v[:400] for k, v in all_pages.items()}, ensure_ascii=False)}

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
    "comparisons": N,
    "synthesis": N,
    "queries": N,
    "orphan_concepts": N,
    "missing_cross_references": N
  }},
  "lint_report_md": "完整的检查报告 Markdown（含 frontmatter）"
}}

检查项：
1. 矛盾声明（两个页面说不同的事情）
2. 孤立概念（没有页面引用它）
3. 缺失概念页（index 提到但没有对应文件）
4. 缺失交叉引用（有概念但页面间没有 [[链接]]
5. 过期声明
6. 数据缺口
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

    report_md = result.get("lint_report_md", "")
    if report_md:
        _write_file("wiki/lint-report.md", report_md)

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    issues_count = len(result.get("issues", []))
    _append_log(f"LINT → 得分: {result.get('score', 'N/A')}, 发现 {issues_count} 个问题")

    return {"status": "ok", "result": result, "usage": usage}
