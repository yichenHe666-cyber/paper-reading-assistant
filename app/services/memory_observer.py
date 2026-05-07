import re
import json
import logging
import struct
import math
from pathlib import Path
from datetime import datetime, timedelta
from difflib import SequenceMatcher

import yaml
from sqlalchemy.orm import Session

from app.services.llm_utils import _call_llm, parse_llm_json_response
from app.models.memory_observation import MemoryObservation
from app.models.memory_entity import MemoryEntity, MemoryEntityLink
from app.models.research_memory import ResearchMemory
from app.config import get_settings

logger = logging.getLogger("paper_reader")

_FUZZY_THRESHOLD = 0.7

_CONSOLIDATION_PROMPT = """你是一位科研经验整合 AI。以下是对同一实体的多条记忆记录。请将它们合并为一条精炼的观察（Observation）。

要求：
- 去重：合并重复信息
- 综合：提炼核心观点
- 保留：保留关键事实和数据
- 标注：如有矛盾，明确指出
- 证据：引用原文关键片段

实体：{entity_name}

记忆记录：
{memories_text}

请以JSON格式返回：
{{"content": "合并后的观察内容（Markdown格式）", "evidence_quotes": ["引用1", "引用2"], "has_contradiction": true/false}}"""

_UPDATE_JUDGMENT_PROMPT = """你是一位科研经验评估 AI。以下是一条已有的观察和一条新记忆。请判断新记忆与观察的关系。

观察：{observation_content}

新记忆：{new_memory_content}

请以JSON格式返回：
{{"relation": "supports|contradicts|extends", "reason": "判断理由", "updated_content": "如果extends，提供更新后的观察内容；否则为null"}}"""


def _slug(text: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"\s+", "-", safe).strip("-")[:60]


class MemoryObserver:

    def consolidate_entity(self, db: Session, entity_name: str) -> MemoryObservation | None:
        try:
            all_entities = db.query(MemoryEntity).all()
            matched_entity_ids = []
            for entity in all_entities:
                ratio = SequenceMatcher(
                    None, entity_name.lower(), entity.name.lower()
                ).ratio()
                if ratio > _FUZZY_THRESHOLD:
                    matched_entity_ids.append(entity.id)

            if not matched_entity_ids:
                return None

            links = db.query(MemoryEntityLink).filter(
                MemoryEntityLink.entity_id.in_(matched_entity_ids)
            ).all()
            memory_ids = list({link.memory_id for link in links})

            if not memory_ids:
                return None

            memories = db.query(ResearchMemory).filter(
                ResearchMemory.id.in_(memory_ids),
                ResearchMemory.is_active == True,
                ResearchMemory.observation_id == None,
            ).all()

            if len(memories) < 3:
                return None

            memories_text = "\n\n".join(
                f"[记忆#{m.id}] ({m.memory_type}) {m.title}\n{m.content}"
                for m in memories
            )

            prompt = _CONSOLIDATION_PROMPT.format(
                entity_name=entity_name,
                memories_text=memories_text,
            )
            messages = [{"role": "user", "content": prompt}]
            content, usage = _call_llm(messages, max_tokens=4096)

            result = parse_llm_json_response(content, "观察整合")

            source_ids = json.dumps([m.id for m in memories], ensure_ascii=False)
            evidence_quotes = json.dumps(
                result.get("evidence_quotes", []), ensure_ascii=False
            )
            freshness_trend = self.compute_freshness_trend(memories)

            avg_confidence = sum(m.confidence for m in memories) / len(memories)
            has_contradiction = result.get("has_contradiction", False)
            confidence = avg_confidence * (0.8 if has_contradiction else 1.0)

            observation = MemoryObservation(
                entity_name=entity_name,
                content=result.get("content", ""),
                source_memory_ids=source_ids,
                evidence_quotes=evidence_quotes,
                proof_count=len(memories),
                freshness_trend=freshness_trend,
                confidence=round(confidence, 2),
            )
            db.add(observation)
            db.flush()

            for m in memories:
                m.observation_id = observation.id

            db.commit()
            db.refresh(observation)

            self._sync_observation_to_obsidian(observation)

            return observation
        except Exception as e:
            logger.error(f"观察整合失败: entity_name={entity_name}, error={e}")
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def update_observation(
        self, db: Session, observation_id: int, new_memory: ResearchMemory
    ) -> MemoryObservation | None:
        try:
            observation = db.query(MemoryObservation).filter(
                MemoryObservation.id == observation_id
            ).first()
            if not observation:
                return None

            prompt = _UPDATE_JUDGMENT_PROMPT.format(
                observation_content=observation.content,
                new_memory_content=new_memory.content,
            )
            messages = [{"role": "user", "content": prompt}]
            content, usage = _call_llm(messages, max_tokens=2048)

            result = parse_llm_json_response(content, "观察更新判断")

            relation = result.get("relation", "supports")

            if relation == "supports":
                observation.proof_count += 1
                observation.freshness_trend = "strengthening"
                existing_ids = json.loads(observation.source_memory_ids)
                existing_ids.append(new_memory.id)
                observation.source_memory_ids = json.dumps(
                    existing_ids, ensure_ascii=False
                )
                new_memory.observation_id = observation.id

            elif relation == "contradicts":
                observation.freshness_trend = "weakening"
                new_observation = MemoryObservation(
                    entity_name=observation.entity_name,
                    content=result.get("updated_content") or new_memory.content,
                    source_memory_ids=json.dumps([new_memory.id], ensure_ascii=False),
                    evidence_quotes=json.dumps([], ensure_ascii=False),
                    proof_count=1,
                    freshness_trend="strengthening",
                    confidence=new_memory.confidence,
                )
                db.add(new_observation)
                db.flush()
                new_memory.observation_id = new_observation.id
                db.commit()
                db.refresh(new_observation)
                self._sync_observation_to_obsidian(new_observation)
                self._sync_observation_to_obsidian(observation)
                return observation

            elif relation == "extends":
                updated_content = result.get("updated_content")
                if updated_content:
                    observation.content = updated_content
                observation.freshness_trend = "stable"
                existing_ids = json.loads(observation.source_memory_ids)
                existing_ids.append(new_memory.id)
                observation.source_memory_ids = json.dumps(
                    existing_ids, ensure_ascii=False
                )
                new_memory.observation_id = observation.id

            db.commit()
            db.refresh(observation)
            self._sync_observation_to_obsidian(observation)

            return observation
        except Exception as e:
            logger.error(
                f"观察更新失败: observation_id={observation_id}, error={e}"
            )
            try:
                db.rollback()
            except Exception:
                pass
            return None

    def compute_freshness_trend(self, source_memories: list) -> str:
        if not source_memories:
            return "stale"

        now = datetime.utcnow()
        total = len(source_memories)
        last_7 = 0
        last_30 = 0
        older_than_30_with_recent = 0
        all_older_90 = True

        for m in source_memories:
            created = m.created_at if m.created_at else now
            age_days = (now - created).days

            if age_days <= 7:
                last_7 += 1
                all_older_90 = False
            elif age_days <= 30:
                last_30 += 1
                all_older_90 = False
            elif age_days <= 90:
                older_than_30_with_recent += 1
                all_older_90 = False
            else:
                older_than_30_with_recent += 1

        if last_7 > total / 2:
            return "strengthening"
        if (last_7 + last_30) > total / 2:
            return "stable"
        if all_older_90:
            return "stale"
        if older_than_30_with_recent > 0 and (last_7 + last_30) > 0:
            return "weakening"
        return "stale"

    def run_consolidation_cycle(self, db: Session) -> dict:
        consolidated = 0
        failed = 0

        try:
            entity_link_counts = {}
            links = db.query(MemoryEntityLink).all()
            for link in links:
                entity_link_counts.setdefault(link.entity_id, set()).add(link.memory_id)

            entity_ids_with_enough = []
            for entity_id, memory_ids in entity_link_counts.items():
                active_unobserved = db.query(ResearchMemory).filter(
                    ResearchMemory.id.in_(memory_ids),
                    ResearchMemory.is_active == True,
                    ResearchMemory.observation_id == None,
                ).count()
                if active_unobserved >= 3:
                    entity_ids_with_enough.append(entity_id)

            if not entity_ids_with_enough:
                return {"consolidated": 0, "failed": 0}

            entities = db.query(MemoryEntity).filter(
                MemoryEntity.id.in_(entity_ids_with_enough)
            ).all()

            for entity in entities:
                result = self.consolidate_entity(db, entity.name)
                if result is not None:
                    consolidated += 1
                else:
                    failed += 1
        except Exception as e:
            logger.error(f"整合周期运行失败: {e}")

        return {"consolidated": consolidated, "failed": failed}

    def _sync_observation_to_obsidian(self, observation: MemoryObservation) -> None:
        try:
            settings = get_settings()
            vault_path = Path(settings.obsidian_vault_path)
            obs_dir = vault_path / "04-科研记忆" / "observations"
            obs_dir.mkdir(parents=True, exist_ok=True)

            entity_slug = _slug(observation.entity_name)
            file_path = obs_dir / f"{entity_slug}.md"

            source_ids = json.loads(observation.source_memory_ids) if observation.source_memory_ids else []
            frontmatter = {
                "observation_id": observation.id,
                "entity_name": observation.entity_name,
                "proof_count": observation.proof_count,
                "freshness_trend": observation.freshness_trend,
                "confidence": observation.confidence,
                "source_memory_ids": source_ids,
                "created": observation.created_at.isoformat() if observation.created_at else None,
                "updated": observation.updated_at.isoformat() if observation.updated_at else None,
            }

            yaml_str = yaml.dump(
                frontmatter, allow_unicode=True, default_flow_style=False
            ).strip()
            file_content = f"---\n{yaml_str}\n---\n\n{observation.content}"

            file_path.write_text(file_content, encoding="utf-8")
        except Exception as e:
            logger.error(f"观察同步Obsidian失败: observation_id={observation.id}, error={e}")


memory_observer = MemoryObserver()
