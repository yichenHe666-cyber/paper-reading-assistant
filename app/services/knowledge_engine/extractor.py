import json
import logging

from app.config import get_settings
from app.services.llm_utils import _call_llm, parse_llm_json_response

logger = logging.getLogger(__name__)


def extract_knowledge(
    parsed_doc,
    existing_wiki_context: str,
    memory_context: str = "",
) -> dict:
    settings = get_settings()

    doc_title = parsed_doc.title or "未命名文档"
    doc_content = parsed_doc.content or ""
    doc_sections = parsed_doc.sections or []
    doc_metadata = parsed_doc.metadata or {}

    sections_text = ""
    for sec in doc_sections[:30]:
        heading = sec.get("heading", "")
        content = sec.get("content", "")
        page = sec.get("page", "")
        loc = f" (第{page}页)" if page else ""
        sections_text += f"\n### {heading}{loc}\n{content[:800]}\n"

    if not sections_text and doc_content:
        chunk_size = 1500
        chunks = [doc_content[i:i+chunk_size] for i in range(0, len(doc_content), chunk_size)]
        sections_text = "\n".join(f"\n### 片段 {i+1}\n{chunk}\n" for i, chunk in enumerate(chunks[:10]))

    context_parts = []
    if existing_wiki_context:
        context_parts.append(f"## 已有 Wiki 概念上下文\n{existing_wiki_context[:2000]}")
    if memory_context:
        context_parts.append(f"## 相关记忆\n{memory_context[:1000]}")
    context_block = "\n\n".join(context_parts) if context_parts else "无"

    prompt = f"""你是一个深度知识提取引擎，负责从学术文档中提取六维结构化知识。

## 文档信息
标题：{doc_title}
作者：{doc_metadata.get('authors', '未知')}
格式：{doc_metadata.get('file_format', '未知')}
类别：{doc_metadata.get('category', '未分类')}

## 文档内容
{sections_text[:6000]}

## 上下文
{context_block}

请从文档中深度提取以下六维知识，以 JSON 返回（只返回 JSON，不要代码块）：

{{
  "concepts": [
    {{
      "name": "概念中文名",
      "name_en": "English Name",
      "definition": "2-3句话的精确定义",
      "one_sentence": "一句话理解",
      "category": "所属学科/领域类别",
      "source_location": "出处定位（章节/页码/公式编号）"
    }}
  ],
  "methods": [
    {{
      "name": "方法名",
      "description": "方法描述",
      "steps": ["步骤1", "步骤2", "步骤3"],
      "applicable_conditions": "适用条件与前提",
      "source_location": "出处定位"
    }}
  ],
  "causal_chains": [
    {{
      "cause": "原因/前提",
      "effect": "结果/推论",
      "reasoning": "推理过程",
      "source_location": "出处定位"
    }}
  ],
  "assumptions": [
    {{
      "assumption": "假设内容",
      "scope": "假设的适用范围",
      "source_location": "出处定位"
    }}
  ],
  "controversies": [
    {{
      "topic": "争议主题",
      "viewpoint_a": "观点A及其论据",
      "viewpoint_b": "观点B及其论据",
      "evidence": "现有证据概述",
      "source_location": "出处定位"
    }}
  ],
  "practical_points": [
    {{
      "point": "实践要点",
      "value": "实践价值",
      "conditions": "适用条件",
      "source_location": "出处定位"
    }}
  ]
}}

提取规则：
1. 每个条目必须有 source_location，精确到章节/页码/公式编号
2. 概念提取要区分核心概念和衍生概念，核心概念优先
3. 方法提取要完整记录步骤和适用条件
4. 因果链要清晰标注推理逻辑
5. 假设要标注适用范围和局限性
6. 争议要客观呈现双方观点和证据
7. 实践要点要标注具体适用条件
8. 如果文档内容不足以提取某个维度，返回空数组
9. 中文输出，术语保留英文原名
10. 概念去重：如果已有 Wiki 概念上下文中存在相同概念，在 name_en 中标注并补充新视角
"""

    messages = [{"role": "user", "content": prompt}]
    max_tokens = settings.knowledge_extraction_max_tokens

    content, usage = _call_llm(messages, max_tokens=max_tokens)

    try:
        knowledge = parse_llm_json_response(content, "knowledge_extraction")
    except Exception as e:
        logger.error(f"知识提取 JSON 解析失败: {e}")
        knowledge = {
            "concepts": [],
            "methods": [],
            "causal_chains": [],
            "assumptions": [],
            "controversies": [],
            "practical_points": [],
        }

    for key in ["concepts", "methods", "causal_chains", "assumptions", "controversies", "practical_points"]:
        if key not in knowledge:
            knowledge[key] = []
        if not isinstance(knowledge[key], list):
            knowledge[key] = []

    for concept in knowledge["concepts"]:
        if "source_location" not in concept or not concept["source_location"]:
            concept["source_location"] = "全文"
    for method in knowledge["methods"]:
        if "source_location" not in method or not method["source_location"]:
            method["source_location"] = "全文"
    for chain in knowledge["causal_chains"]:
        if "source_location" not in chain or not chain["source_location"]:
            chain["source_location"] = "全文"
    for assumption in knowledge["assumptions"]:
        if "source_location" not in assumption or not assumption["source_location"]:
            assumption["source_location"] = "全文"
    for controversy in knowledge["controversies"]:
        if "source_location" not in controversy or not controversy["source_location"]:
            controversy["source_location"] = "全文"
    for point in knowledge["practical_points"]:
        if "source_location" not in point or not point["source_location"]:
            point["source_location"] = "全文"

    knowledge["_usage"] = usage
    return knowledge
