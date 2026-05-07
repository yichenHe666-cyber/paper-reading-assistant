import json
import logging

from app.services.llm_utils import _call_llm, parse_llm_json_response

logger = logging.getLogger(__name__)

VALID_RELATION_TYPES = [
    "depends_on",
    "extends",
    "contradicts",
    "analogous",
    "part_of",
    "evolves_from",
]


def link_concepts(new_concepts: list, existing_concepts: list) -> list:
    if not new_concepts or not existing_concepts:
        return _link_new_concepts_only(new_concepts)

    new_names = []
    for c in new_concepts:
        name = c.get("name", "") if isinstance(c, dict) else str(c)
        if name:
            new_names.append(name)

    if not new_names:
        return []

    existing_list = existing_concepts if isinstance(existing_concepts, list) else []
    existing_str = ", ".join(str(c) for c in existing_list[:50])
    new_str = ", ".join(new_names[:30])

    prompt = f"""你是知识图谱概念链接专家。请判断新概念与已有概念之间的关系。

## 新概念
{new_str}

## 已有概念
{existing_str}

请以 JSON 返回（只返回 JSON，不要代码块）：
{{
  "edges": [
    {{
      "source_concept": "概念名（来自新概念）",
      "target_concept": "概念名（来自已有概念）",
      "relation_type": "关系类型",
      "strength": 0.8,
      "evidence": "判断依据"
    }}
  ]
}}

关系类型必须是以下之一：
- depends_on: 新概念依赖于已有概念
- extends: 新概念扩展了已有概念
- contradicts: 新概念与已有概念矛盾
- analogous: 新概念与已有概念类似/类比
- part_of: 新概念是已有概念的一部分
- evolves_from: 新概念从已有概念演化而来

规则：
1. 只建立确实存在的关系，不要强行关联
2. strength 范围 0.0-1.0，1.0 表示确定性最强
3. 每个新概念最多关联 3 个已有概念
4. 如果没有明确关系，返回空 edges 数组
5. evidence 必须简述判断依据
6. 如果发现 contradicts 关系，evidence 中要标注矛盾点
"""

    messages = [{"role": "user", "content": prompt}]
    content, usage = _call_llm(messages, max_tokens=2000)

    try:
        result = parse_llm_json_response(content, "concept_linking")
    except Exception as e:
        logger.error(f"概念链接 JSON 解析失败: {e}")
        return []

    edges = result.get("edges", [])
    valid_edges = []
    for edge in edges:
        relation = edge.get("relation_type", "")
        if relation in VALID_RELATION_TYPES:
            edge["contradiction_flag"] = relation == "contradicts"
            valid_edges.append(edge)

    return valid_edges


def _link_new_concepts_only(new_concepts: list) -> list:
    if not new_concepts or len(new_concepts) < 2:
        return []

    names = []
    for c in new_concepts:
        name = c.get("name", "") if isinstance(c, dict) else str(c)
        if name:
            names.append(name)

    if len(names) < 2:
        return []

    names_str = ", ".join(names[:30])

    prompt = f"""你是知识图谱概念链接专家。请判断以下概念之间的内部关系。

## 概念列表
{names_str}

请以 JSON 返回（只返回 JSON，不要代码块）：
{{
  "edges": [
    {{
      "source_concept": "概念A",
      "target_concept": "概念B",
      "relation_type": "关系类型",
      "strength": 0.8,
      "evidence": "判断依据"
    }}
  ]
}}

关系类型必须是以下之一：
- depends_on: A 依赖于 B
- extends: A 扩展了 B
- contradicts: A 与 B 矛盾
- analogous: A 与 B 类似
- part_of: A 是 B 的一部分
- evolves_from: A 从 B 演化而来

规则：
1. 只建立确实存在的关系
2. strength 范围 0.0-1.0
3. 如果没有明确关系，返回空 edges 数组
4. evidence 必须简述判断依据
"""

    messages = [{"role": "user", "content": prompt}]
    content, usage = _call_llm(messages, max_tokens=2000)

    try:
        result = parse_llm_json_response(content, "concept_internal_linking")
    except Exception as e:
        logger.error(f"概念内部链接 JSON 解析失败: {e}")
        return []

    edges = result.get("edges", [])
    valid_edges = []
    for edge in edges:
        relation = edge.get("relation_type", "")
        if relation in VALID_RELATION_TYPES:
            edge["contradiction_flag"] = relation == "contradicts"
            valid_edges.append(edge)

    return valid_edges
