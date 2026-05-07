import json
import logging

from app.database.session import SessionLocal
from app.models.research_memory import ResearchMemory
from app.services.llm_utils import _call_llm, parse_llm_json_response
from app.services.memory_engine import memory_engine
from app.services.memory_entity_engine import memory_entity_engine

logger = logging.getLogger("paper_reader")


class MemoryDistiller:

    def distill_reading_session(self, paper_id: int, reading_result: dict) -> dict:
        db = SessionLocal()
        try:
            existing_memories = (
                db.query(ResearchMemory)
                .filter(
                    ResearchMemory.source_paper_id == paper_id,
                    ResearchMemory.is_active == True,
                )
                .all()
            )
            existing_memories_summary = self._format_existing_memories(existing_memories)

            prompt = self._build_prompt(paper_id, reading_result, existing_memories_summary)

            try:
                messages = [{"role": "user", "content": prompt}]
                content, usage = _call_llm(messages, max_tokens=4096)
            except Exception as e:
                logger.error(f"记忆蒸馏 LLM 调用失败: paper_id={paper_id}, error={e}")
                return {"status": "error", "message": str(e), "memories_created": 0}

            try:
                result = parse_llm_json_response(content, "蒸馏器")
            except Exception as e:
                logger.error(f"记忆蒸馏 JSON 解析失败: paper_id={paper_id}, error={e}")
                return {"status": "error", "message": str(e), "memories_created": 0, "usage": usage}

            memories_created = 0
            category_type_map = {
                "preferences": "preference",
                "experiences": "experience",
                "directions": "direction",
                "connections": "connection",
            }

            for category, memory_type in category_type_map.items():
                items = result.get(category, [])
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title", "")
                    content_text = item.get("content", "")
                    tags = item.get("tags", [])
                    entities = item.get("entities", [])
                    if not title or not content_text:
                        continue
                    try:
                        memory = memory_engine.remember(
                            db,
                            memory_type,
                            title,
                            content_text,
                            tags,
                            paper_id,
                            "auto_distill",
                            0.7,
                        )
                        memories_created += 1
                        if entities and memory:
                            try:
                                memory_entity_engine.link_memory_entities(db, memory.id, entities)
                            except Exception as ee:
                                logger.error(f"实体链接失败: memory_id={memory.id}, error={ee}")
                    except Exception as e:
                        logger.error(
                            f"记忆存储失败: paper_id={paper_id}, type={memory_type}, title={title}, error={e}"
                        )

            logger.info(
                f"记忆蒸馏完成: paper_id={paper_id}, memories_created={memories_created}"
            )
            return {"status": "ok", "memories_created": memories_created, "usage": usage}

        except Exception as e:
            logger.error(f"记忆蒸馏异常: paper_id={paper_id}, error={e}")
            return {"status": "error", "message": str(e), "memories_created": 0}
        finally:
            db.close()

    def _format_existing_memories(self, memories: list) -> str:
        if not memories:
            return "暂无已有相关记忆"
        lines = []
        for m in memories:
            tags_str = ""
            try:
                tags_list = json.loads(m.tags) if m.tags else []
                tags_str = ", ".join(tags_list)
            except (json.JSONDecodeError, TypeError):
                tags_str = str(m.tags) if m.tags else ""
            lines.append(
                f"- [{m.memory_type}] {m.title}（置信度: {m.confidence}，标签: {tags_str}）"
            )
        return "\n".join(lines)

    def _build_prompt(self, paper_id: int, reading_result: dict, existing_memories_summary: str) -> str:
        paper = reading_result.get("paper", {})
        r1_output = reading_result.get("r1_output", {})
        r2_formal = reading_result.get("r2_formal", {})
        r2_critical = reading_result.get("r2_critical", {})
        r3_note = reading_result.get("r3_note", "")
        reading_history = reading_result.get("reading_history", {})

        title = paper.get("title", "未知")
        authors = paper.get("authors", "未知")
        year = paper.get("year", "未知")
        topic_id = paper.get("topic_id", "未知")
        paper_type = r1_output.get("paper_type", "未知")
        math_intensity = r1_output.get("math_intensity", "未知")

        five_c_json = json.dumps(r1_output.get("5c_summary", {}), ensure_ascii=False)
        strategy_json = json.dumps(r1_output.get("reading_strategy", {}), ensure_ascii=False)
        warnings_json = json.dumps(r1_output.get("warning_flags", []), ensure_ascii=False)

        formal_summary = json.dumps(
            {
                "symbol_table": r2_formal.get("symbol_table", {}),
                "theorems": r2_formal.get("theorems", []),
                "derivation_checks": r2_formal.get("derivation_checks", []),
                "boundary_conditions": r2_formal.get("boundary_conditions", []),
                "formal_gaps": r2_formal.get("formal_gaps", []),
            },
            ensure_ascii=False,
        )

        findings_json = json.dumps(
            {
                "findings": r2_critical.get("findings", []),
                "cross_paper_findings": r2_critical.get("cross_paper_findings", []),
            },
            ensure_ascii=False,
        )

        r3_note_first_2000 = r3_note[:2000] if r3_note else "无笔记"

        duration_seconds = reading_history.get("duration_seconds", 0)
        rating = reading_history.get("rating")
        reading_behavior = f"阅读时长: {duration_seconds}秒"
        if rating is not None:
            reading_behavior += f"，评分: {rating}"

        prompt = f"""你是一位科研经验蒸馏 AI。你的任务是从一次完整的论文阅读会话中提取四类科研记忆。

## 论文信息
标题：{title}
作者：{authors}
年份：{year}
类型：{paper_type}
数学强度：{math_intensity}
主题：{topic_id}

## 第一遍分析（R1）
5C摘要：{five_c_json}
阅读策略：{strategy_json}
警告标志：{warnings_json}

## 第二遍分析（R2）
形式化拆解摘要：{formal_summary}
批判审查发现：{findings_json}

## 第三遍笔记（R3）摘要
{r3_note_first_2000}

## 阅读行为
{reading_behavior}

## 已有相关记忆
{existing_memories_summary}

请以 JSON 返回蒸馏结果（只返回 JSON，不要代码块）：

{{
  "preferences": [
    {{
      "title": "偏好标题（≤50字）",
      "content": "偏好描述（Markdown格式，含具体数据支撑）",
      "tags": ["标签1", "标签2"],
      "entities": [{{"name": "实体名", "type": "concept|method|person|institution|topic"}}]
    }}
  ],
  "experiences": [
    {{
      "title": "经验标题（≤50字）",
      "content": "经验描述（Markdown格式，含具体场景和建议）",
      "tags": ["标签1", "标签2"],
      "entities": [{{"name": "实体名", "type": "concept|method|person|institution|topic"}}]
    }}
  ],
  "directions": [
    {{
      "title": "方向标题（≤50字）",
      "content": "方向评估（Markdown格式，含是否值得深入的判断和理由）",
      "tags": ["标签1", "标签2"],
      "entities": [{{"name": "实体名", "type": "concept|method|person|institution|topic"}}]
    }}
  ],
  "connections": [
    {{
      "title": "关联标题（≤50字）",
      "content": "关联描述（Markdown格式，含论文间的具体关系）",
      "tags": ["标签1", "标签2"],
      "entities": [{{"name": "实体名", "type": "concept|method|person|institution|topic"}}]
    }}
  ]
}}

蒸馏规则：
- 偏好：从阅读行为推断用户的论文类型偏好、数学强度偏好、阅读深度偏好
- 经验：评估阅读策略是否匹配论文类型，LLM输出质量如何，哪些步骤可以优化
- 方向：评估该论文所在方向的研究价值，是否值得深入
- 关联：提取跨论文的概念关联、方法对比、演进关系
- 每类最多提取 3 条，只提取有价值的记忆，宁缺毋滥
- 如果某类没有值得记录的内容，返回空数组
- 标签使用中文，简洁精准
- 实体提取：从每条记忆中提取科研相关实体（概念、方法、人物、机构、主题），每条最多5个"""
        return prompt


memory_distiller = MemoryDistiller()
