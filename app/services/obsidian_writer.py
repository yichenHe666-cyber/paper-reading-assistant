import re
import json
import logging
from pathlib import Path
from datetime import date
from app.config import get_settings
from app.database.session import SessionLocal
from app.services.snapshot_manager import snapshot_before_write


class ObsidianWriter:

    def __init__(self):
        settings = get_settings()
        self.vault_path = Path(settings.obsidian_vault_path)
        self.paper_dir = self.vault_path / "01-论文精读"
        self.concept_dir = self.vault_path / "02-概念卡片"
        self.vocab_dir = self.vault_path / "03-专业词汇"

    def write_paper_note(self, paper: dict, note_draft: str) -> str:
        topic = paper.get("topic_id", "other").replace("_", " ")
        folder = self.paper_dir / topic
        folder.mkdir(parents=True, exist_ok=True)
        filename = safe_filename(paper.get("title", "untitled")) + ".md"
        filepath = folder / filename

        today = str(date.today())

        has_new_format = ("## 3. 形式化拆解" in note_draft and "## 4. 批判性审查" in note_draft)

        if has_new_format:
            if filepath.exists():
                existing_content = filepath.read_text(encoding="utf-8")
                db = SessionLocal()
                try:
                    snapshot_before_write(db, paper.get("id"), str(filepath), existing_content)
                finally:
                    db.close()
            filepath.write_text(note_draft, encoding="utf-8")
            logging.getLogger("paper_reader").info(f"[obsidian] Wrote academic note: {filepath}")
            return str(filepath)

        if not note_draft.strip().startswith("---"):
            concepts_list = paper.get("concepts", "[]")
            if isinstance(concepts_list, str):
                try:
                    concepts_list = json.loads(concepts_list)
                except json.JSONDecodeError:
                    concepts_list = []
            concepts_yaml = "\n".join([f'  - "[[{c}]]"' for c in concepts_list])
            tags_str = paper.get("tags", "经典")
            note_draft = f"""---
type: paper
source: papers-we-love
topic: {topic}
subtopic: {paper.get('subtopic', '') or ''}
authors: {paper.get('authors', '[]')}
year: {paper.get('year', '')}
venue: "{paper.get('venue', '') or ''}"
read_status: 精读中
difficulty: {paper.get('difficulty', '中等')}
rating: 
created: {today}
last_read: {today}
tags: [{tags_str}]
concepts: {paper.get('concepts', '[]')}
related_papers: []
---

# {paper.get('title', '')}

> **一句话总结**：(读完后来写)

## 📌 为什么读这篇

{paper.get('abstract', '')}

## 🧠 核心概念

## 🔗 与我已知知识的联系

## ❓ 我没看懂的地方

## 📝 我的思考

## 📎 参考资料

- PDF链接：{paper.get('pdf_url', '')}
- Papers We Love 社区笔记：{paper.get('community_notes_url', '') or ''}
---
*由经典论文精读助手生成 | 源仓库: papers-we-love*
"""

        if filepath.exists():
            existing_content = filepath.read_text(encoding="utf-8")
            db = SessionLocal()
            try:
                snapshot_before_write(db, paper.get("id"), str(filepath), existing_content)
            finally:
                db.close()

        filepath.write_text(note_draft, encoding="utf-8")
        logging.getLogger("paper_reader").info(f"[obsidian] Wrote paper note: {filepath}")
        return str(filepath)

    def write_concept_card(self, concept: dict) -> str:
        if not isinstance(concept, dict):
            logging.getLogger("paper_reader").warning(f"[obsidian] Skipping non-dict concept card: {type(concept)}")
            return ""
        self.concept_dir.mkdir(parents=True, exist_ok=True)
        filename = safe_filename(concept.get("name", concept.get("name_en", "concept"))) + ".md"
        filepath = self.concept_dir / filename

        related = concept.get("related_concepts", [])
        related_links = "\n".join([f'  - "[[{r}]]"' for r in related])
        papers = concept.get("related_papers", [])
        paper_links = "\n".join([f'  - "[[{p}]]"' for p in papers])
        today = str(date.today())

        content = f"""---
type: concept
name: "{concept.get('name', concept.get('name_en', ''))}"
aliases: ["{concept.get('name_en', '')}"]
category: "{concept.get('category', '')}"
difficulty: {concept.get('difficulty', '中等')}
formal_definition: "{concept.get('formal_definition', concept.get('definition', ''))}"
context_in_paper: "{concept.get('context_in_paper', '')}"
evolution_line: "{concept.get('evolution_line', '')}"
related_papers:
{paper_links}
related_concepts:
{related_links}
tags:
  - 概念卡片
created: {today}
source: llm_generated
---

# {concept.get('name', concept.get('name_en', ''))}

## 📖 学术定义

{concept.get('formal_definition', concept.get('definition', ''))}

## 💬 一句话理解

> {concept.get('one_sentence', '')}

## 📌 在本论文中的上下文

{concept.get('context_in_paper', '')}

## 🔄 概念演进

{concept.get('evolution_line', '（在此填写该概念在学术史上的演进关系）')}

## 📎 关联论文

{chr(10).join([f'- [[{p}]]' for p in papers])}

## 📝 我的笔记

（在此填写自己的理解）

---
*由学术论文精读助手生成*
"""
        filepath.write_text(content, encoding="utf-8")
        return str(filepath)

    def write_vocabulary(self, paper: dict, vocabulary_md: str) -> str:
        self.vocab_dir.mkdir(parents=True, exist_ok=True)
        filename = safe_filename(paper.get("title", "untitled")) + " 词汇.md"
        filepath = self.vocab_dir / filename

        if not vocabulary_md.strip().startswith("---"):
            filepath.write_text(vocabulary_md, encoding="utf-8")
            return str(filepath)

        filepath.write_text(vocabulary_md, encoding="utf-8")
        return str(filepath)

    def write_all(self, paper: dict, note_draft: str, concept_cards: list[dict], vocabulary_md: str) -> dict:
        paper_path = self.write_paper_note(paper, note_draft)
        concept_paths = []
        for card in concept_cards:
            cp = self.write_concept_card(card)
            if cp:
                concept_paths.append(cp)
        vocab_path = self.write_vocabulary(paper, vocabulary_md)
        return {
            "paper_path": paper_path,
            "concept_paths": concept_paths,
            "vocab_path": vocab_path,
        }

    def write_dashboard(self) -> str:
        dash_dir = self.vault_path / "03-阅读计划"
        dash_dir.mkdir(parents=True, exist_ok=True)
        filepath = dash_dir / "阅读统计.md"

        today = str(date.today())
        content = f"""---
type: dashboard
title: 阅读统计
created: {today}
updated: {today}
---

# 📊 阅读统计

## 论文精读进度

```dataview
TABLE 
  topic as 主题,
  difficulty as 难度,
  read_status as 状态,
  last_read as 最后阅读,
  rating as 评分
FROM "01-论文精读"
SORT last_read DESC
```

## 概念卡片概览

```dataview
TABLE 
  category as 类别,
  length(filter(file.inlinks, (x) => contains(x.path, "01-论文精读"))) as 关联论文数,
  difficulty as 难度
FROM "02-概念卡片"
SORT category ASC
```

## 专业词汇概览

```dataview
TABLE
  topic as 主题,
  file.cday as 创建日期
FROM "03-专业词汇"
SORT file.cday DESC
```

---
*由经典论文精读助手自动生成*
"""
        filepath.write_text(content, encoding="utf-8")
        return str(filepath)


def safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "-", name)
    name = name.strip(". ")
    if len(name) > 100:
        name = name[:100]
    return name
