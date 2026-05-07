import json
import logging

from sqlalchemy.orm import Session

from app.services.llm_utils import _call_llm, parse_llm_json_response
from app.services.memory_engine import memory_engine
from app.models.memory_observation import MemoryObservation
from app.models.research_memory import ResearchMemory
from app.models.memory_entity import MemoryEntity, MemoryEntityLink

logger = logging.getLogger("paper_reader")

_REFLECTION_PROMPT = """你是一位科研反思 AI。基于以下记忆和观察，进行深度推理分析。

查询主题：{query}

## 相关记忆
{memories_text}

## 相关观察
{observations_text}

请进行深度反思，以JSON格式返回：
{{"insights": ["新见解1", "新见解2"], "contradictions": ["矛盾1"], "trends": ["趋势预测1"], "actions": ["行动建议1"]}}

反思规则：
- insights：从记忆中发现的非显而易见的新见解
- contradictions：记忆间的矛盾或不一致
- trends：基于记忆时间线的趋势预测
- actions：基于分析的具体行动建议
- 宁缺毋滥，只返回有价值的发现"""


class MemoryReflector:

    def reflect(self, db: Session, query: str, entity_name: str = None) -> dict:
        empty_result = {
            "insights": [],
            "contradictions": [],
            "trends": [],
            "actions": [],
            "raw_response": "",
        }
        try:
            memories = memory_engine.recall(db, query=query, limit=15)

            observations = []
            if entity_name:
                entity_obs = (
                    db.query(MemoryObservation)
                    .filter(MemoryObservation.entity_name == entity_name)
                    .all()
                )
                observations.extend(entity_obs)

            memory_ids = [m.id for m in memories]
            if memory_ids:
                try:
                    links = (
                        db.query(MemoryEntityLink)
                        .filter(MemoryEntityLink.memory_id.in_(memory_ids))
                        .all()
                    )
                    entity_ids = list({l.entity_id for l in links})
                    if entity_ids:
                        entities = (
                            db.query(MemoryEntity)
                            .filter(MemoryEntity.id.in_(entity_ids))
                            .all()
                        )
                        entity_names = [e.name for e in entities]
                        if entity_names:
                            existing_obs_ids = {o.id for o in observations}
                            related_obs = (
                                db.query(MemoryObservation)
                                .filter(MemoryObservation.entity_name.in_(entity_names))
                                .all()
                            )
                            for obs in related_obs:
                                if obs.id not in existing_obs_ids:
                                    observations.append(obs)
                except Exception as e:
                    logger.error(f"反思：查询关联实体观察失败: {e}")

            memories_text = self._format_memories(memories)
            observations_text = self._format_observations(observations)

            prompt = _REFLECTION_PROMPT.format(
                query=query,
                memories_text=memories_text,
                observations_text=observations_text,
            )

            try:
                messages = [{"role": "user", "content": prompt}]
                content, usage = _call_llm(messages, max_tokens=4096)
            except Exception as e:
                logger.error(f"反思 LLM 调用失败: query={query}, error={e}")
                return empty_result

            try:
                result = parse_llm_json_response(content, "反思")
            except Exception as e:
                logger.error(f"反思 JSON 解析失败: query={query}, error={e}")
                empty_result["raw_response"] = content
                return empty_result

            return {
                "insights": result.get("insights", []) if isinstance(result.get("insights"), list) else [],
                "contradictions": result.get("contradictions", []) if isinstance(result.get("contradictions"), list) else [],
                "trends": result.get("trends", []) if isinstance(result.get("trends"), list) else [],
                "actions": result.get("actions", []) if isinstance(result.get("actions"), list) else [],
                "raw_response": content,
            }

        except Exception as e:
            logger.error(f"反思异常: query={query}, error={e}")
            return empty_result

    def save_reflection_as_memory(
        self,
        db: Session,
        reflection_result: dict,
        query: str,
        entity_name: str = None,
        auto: bool = False,
    ) -> ResearchMemory | None:
        try:
            title = f"反思: {entity_name}" if entity_name else f"反思: {query[:30]}"

            parts = []
            insights = reflection_result.get("insights", [])
            if insights:
                parts.append("## 新见解\n" + "\n".join(f"- {i}" for i in insights))
            contradictions = reflection_result.get("contradictions", [])
            if contradictions:
                parts.append("## 矛盾发现\n" + "\n".join(f"- {c}" for c in contradictions))
            trends = reflection_result.get("trends", [])
            if trends:
                parts.append("## 趋势预测\n" + "\n".join(f"- {t}" for t in trends))
            actions = reflection_result.get("actions", [])
            if actions:
                parts.append("## 行动建议\n" + "\n".join(f"- {a}" for a in actions))

            content = "\n\n".join(parts) if parts else "反思未产生有效内容"

            source_type = "auto_reflection" if auto else "reflection"
            confidence = 0.6 if auto else 0.7

            memory = memory_engine.remember(
                db,
                memory_type="experience",
                title=title,
                content=content,
                tags=["反思", entity_name] if entity_name else ["反思"],
                source_type=source_type,
                confidence=confidence,
            )
            return memory

        except Exception as e:
            logger.error(f"保存反思记忆失败: query={query}, error={e}")
            return None

    def _format_memories(self, memories: list) -> str:
        if not memories:
            return "暂无相关记忆"
        lines = []
        for m in memories:
            tags_str = ""
            try:
                tags_list = json.loads(m.tags) if m.tags else []
                tags_str = ", ".join(tags_list)
            except (json.JSONDecodeError, TypeError):
                tags_str = str(m.tags) if m.tags else ""
            lines.append(
                f"- [{m.memory_type}] {m.title}（置信度: {m.confidence}，标签: {tags_str}）\n  {m.content[:200]}"
            )
        return "\n".join(lines)

    def _format_observations(self, observations: list) -> str:
        if not observations:
            return "暂无相关观察"
        lines = []
        for obs in observations:
            lines.append(
                f"- [{obs.entity_name}] {obs.content[:200]}（置信度: {obs.confidence}，证明次数: {obs.proof_count}）"
            )
        return "\n".join(lines)


memory_reflector = MemoryReflector()
