import json
from app.services.llm_service_base import BaseLLMService
from app.services.llm_prompt_builder import PromptBuilder


class NoteDraftService(BaseLLMService):

    def __init__(self):
        super().__init__("笔记草稿")

    def build_prompt(self, paper: dict, navigator: dict) -> str:
        concepts_list = [c["term"] for c in navigator.get("core_concepts", [])]

        builder = PromptBuilder(
            role="计算机科学导论助教",
            task_description="正在帮助大一本科生整理经典论文的阅读笔记",
        )
        builder.add_paper_context(paper)
        builder.add_context("子主题", paper.get("subtopic", ""))
        builder.add_context("为什么读", navigator.get("why_read", ""))
        builder.add_context("核心概念", json.dumps(navigator.get("core_concepts", []), ensure_ascii=False))
        builder.add_context("背景知识", navigator.get("background_notes", ""))
        builder.add_context("阅读建议", json.dumps(navigator.get("reading_tips", {}), ensure_ascii=False))
        builder.add_context("思考题", json.dumps(navigator.get("discussion_questions", []), ensure_ascii=False))

        template = f"""---
type: paper
source: papers-we-love
topic: {paper.get('topic_id', '').replace('_', ' ')}
subtopic: {paper.get('subtopic', '') or ''}
authors: {paper.get('authors', '[]')}
year: {paper.get('year', '')}
venue: "{paper.get('venue', '') or ''}"
read_status: 未读
difficulty: 中等
rating: 
created: (当前日期)
last_read: 
tags: []
concepts: {json.dumps(concepts_list, ensure_ascii=False)}
related_papers: []
---

# {paper.get('title', '')}

> **一句话总结**：(用一句话说清这篇论文解决了什么问题)

## 📌 为什么读这篇

{navigator.get('why_read', '')}

## 🧠 核心概念

（为每个核心概念写一个小节，解释它是什么，为什么重要）

## 🔗 与我已知知识的联系

（启发大一学生将论文概念与已学知识连接起来，比如数学分析、线性代数、编程基础等）

## ❓ 我没看懂的地方

（留空，让用户填写）

## 📝 我的思考

（留空，让用户填写）

## 📎 参考资料

- PDF链接：{paper.get('pdf_url', '')}
- Papers We Love 社区笔记：{paper.get('community_notes_url', '')}
{"".join([f'- 概念卡片: [[{c}]]\n' for c in concepts_list])}
---
*由经典论文精读助手生成 | 源仓库: papers-we-love*"""

        builder.add_raw_section(
            "请生成完整的 Markdown 论文笔记（直接返回 Markdown，不要用代码块包裹）。格式如下：",
            template,
        )
        return builder.build()


def _strip_code_block(content: str) -> str:
    if content.startswith("```markdown"):
        return "\n".join(content.split("\n")[1:-1])
    elif content.startswith("```"):
        return "\n".join(content.split("\n")[1:-1])
    return content


def generate_note_draft(paper: dict, navigator: dict) -> str:
    service = NoteDraftService()
    content, usage = service.execute(
        paper=paper, navigator=navigator,
        max_tokens=2500, enable_json_parsing=False,
    )
    return _strip_code_block(content), usage
