import json
import logging
import math
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.services.llm_utils import _call_llm, parse_llm_json_response
from app.models.memory_entity import MemoryEntity, MemoryEntityLink
from app.models.research_memory import ResearchMemory

logger = logging.getLogger("paper_reader")

_ENTITY_EXTRACTION_PROMPT = """从以下文本中提取科研相关的实体。实体类型包括：concept（概念）、method（方法）、person（人物）、institution（机构）、topic（主题/领域）。

最多提取10个实体。只提取明确出现的实体，不要推断。

文本：
{text}

以JSON格式返回，只返回JSON：
{{"entities": [{{"name": "实体名", "type": "concept|method|person|institution|topic"}}]}}"""

_VALID_ENTITY_TYPES = {"concept", "method", "person", "institution", "topic"}

_RESOLVE_THRESHOLD = 0.85
_QUERY_MATCH_THRESHOLD = 0.7


class MemoryEntityEngine:

    def extract_entities(self, text: str) -> list[dict]:
        if not text or not text.strip():
            return []
        try:
            prompt = _ENTITY_EXTRACTION_PROMPT.format(text=text)
            messages = [{"role": "user", "content": prompt}]
            content, usage = _call_llm(messages, max_tokens=1024)
            result = parse_llm_json_response(content, "实体提取")
            entities = result.get("entities", [])
            if not isinstance(entities, list):
                return []
            valid = []
            for e in entities:
                if not isinstance(e, dict):
                    continue
                name = e.get("name", "").strip()
                etype = e.get("type", "").strip()
                if name and etype in _VALID_ENTITY_TYPES:
                    valid.append({"name": name, "type": etype})
                if len(valid) >= 10:
                    break
            return valid
        except Exception as e:
            logger.error(f"实体提取失败: {e}")
            return []

    def resolve_entity(self, db: Session, name: str, entity_type: str) -> MemoryEntity | None:
        try:
            existing_entities = db.query(MemoryEntity).filter(
                MemoryEntity.entity_type == entity_type
            ).all()
            for entity in existing_entities:
                ratio = SequenceMatcher(
                    None, name.lower(), entity.name.lower()
                ).ratio()
                if ratio > _RESOLVE_THRESHOLD:
                    return entity
            new_entity = MemoryEntity(name=name, entity_type=entity_type)
            db.add(new_entity)
            db.flush()
            return new_entity
        except Exception as e:
            logger.error(f"实体解析失败: name={name}, type={entity_type}, error={e}")
            return None

    def link_memory_entities(self, db: Session, memory_id: int, entities: list[dict]):
        if not entities:
            return
        for ent in entities:
            try:
                entity = self.resolve_entity(db, ent["name"], ent["type"])
                if entity is None:
                    continue
                existing_link = db.query(MemoryEntityLink).filter(
                    MemoryEntityLink.memory_id == memory_id,
                    MemoryEntityLink.entity_id == entity.id,
                ).first()
                if existing_link:
                    continue
                link = MemoryEntityLink(memory_id=memory_id, entity_id=entity.id)
                db.add(link)
            except Exception as e:
                logger.error(
                    f"记忆实体关联失败: memory_id={memory_id}, entity={ent}, error={e}"
                )
        try:
            db.flush()
        except Exception as e:
            logger.error(f"记忆实体关联flush失败: memory_id={memory_id}, error={e}")

    def find_memories_by_entity(self, db: Session, entity_name: str) -> list[ResearchMemory]:
        try:
            all_entities = db.query(MemoryEntity).all()
            matched_entity_ids = []
            for entity in all_entities:
                ratio = SequenceMatcher(
                    None, entity_name.lower(), entity.name.lower()
                ).ratio()
                if ratio > _QUERY_MATCH_THRESHOLD:
                    matched_entity_ids.append(entity.id)
            if not matched_entity_ids:
                return []
            links = db.query(MemoryEntityLink).filter(
                MemoryEntityLink.entity_id.in_(matched_entity_ids)
            ).all()
            memory_ids = list({link.memory_id for link in links})
            if not memory_ids:
                return []
            memories = db.query(ResearchMemory).filter(
                ResearchMemory.id.in_(memory_ids),
                ResearchMemory.is_active == True,
            ).all()
            return memories
        except Exception as e:
            logger.error(f"按实体查找记忆失败: entity_name={entity_name}, error={e}")
            return []

    def find_entities_in_query(self, db: Session, query: str) -> list[MemoryEntity]:
        try:
            all_entities = db.query(MemoryEntity).all()
            matched = []
            query_lower = query.lower()
            for entity in all_entities:
                if entity.name.lower() in query_lower:
                    matched.append(entity)
                    continue
                ratio = SequenceMatcher(
                    None, query_lower, entity.name.lower()
                ).ratio()
                if ratio > _QUERY_MATCH_THRESHOLD:
                    matched.append(entity)
            return matched
        except Exception as e:
            logger.error(f"查询实体匹配失败: query={query}, error={e}")
            return []

    def get_entity_memory_ids(self, db: Session, entity_ids: list[int]) -> set[int]:
        if not entity_ids:
            return set()
        try:
            links = db.query(MemoryEntityLink).filter(
                MemoryEntityLink.entity_id.in_(entity_ids)
            ).all()
            return {link.memory_id for link in links}
        except Exception as e:
            logger.error(f"获取实体关联记忆ID失败: entity_ids={entity_ids}, error={e}")
            return set()


memory_entity_engine = MemoryEntityEngine()
