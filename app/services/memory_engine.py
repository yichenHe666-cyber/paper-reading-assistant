import re
import json
import math
from pathlib import Path
from datetime import datetime, timedelta

import yaml
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.research_memory import ResearchMemory
from app.services.memory_vectorizer import memory_vectorizer
from app.services.memory_entity_engine import memory_entity_engine
from app.models.memory_observation import MemoryObservation


def _slug(text: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"\s+", "-", safe).strip("-")[:60]


def _parse_tags(tags_str) -> list:
    if not tags_str:
        return []
    if isinstance(tags_str, list):
        return tags_str
    try:
        parsed = json.loads(tags_str)
        if isinstance(parsed, list):
            return parsed
        return []
    except (json.JSONDecodeError, TypeError):
        return []


class MemoryEngine:

    def remember(
        self,
        db: Session,
        memory_type: str,
        title: str,
        content: str,
        tags=None,
        source_paper_id=None,
        source_type="auto_distill",
        confidence=1.0,
    ) -> ResearchMemory:
        if tags is None:
            tags = []
        if isinstance(tags, str):
            tags = _parse_tags(tags)

        memory = ResearchMemory(
            memory_type=memory_type,
            title=title,
            content=content,
            tags=json.dumps(tags, ensure_ascii=False),
            source_paper_id=source_paper_id,
            source_type=source_type,
            confidence=confidence,
            access_count=0,
            is_active=True,
        )
        db.add(memory)
        db.flush()

        db.commit()
        db.refresh(memory)

        try:
            embedding = memory_vectorizer.embed_text(f"{memory.title} {memory.content}")
            if embedding is not None:
                memory.embedding = memory_vectorizer._encode_embedding(embedding)
                memory.embedding_model = memory_vectorizer._embedding_model if memory_vectorizer._provider == "ollama" else memory_vectorizer._openai_model
                db.commit()
        except Exception:
            pass

        self._sync_to_obsidian(memory)
        return memory

    def recall(
        self,
        db: Session,
        query: str,
        memory_types=None,
        tags=None,
        limit=10,
        min_confidence=0.0,
    ) -> list:
        weights = [float(w) for w in get_settings().memory_search_weights.split(",")]
        semantic_w, keyword_w, entity_w = weights[0], weights[1], weights[2]

        semantic_results = {}
        keyword_results = {}
        entity_results = {}

        query_embedding = memory_vectorizer.embed_query(query)

        if query_embedding is not None:
            all_with_emb = (
                db.query(ResearchMemory)
                .filter(
                    ResearchMemory.is_active == True,
                    ResearchMemory.embedding.isnot(None),
                )
                .all()
            )
            scored = []
            for m in all_with_emb:
                vec = memory_vectorizer._decode_embedding(m.embedding)
                sim = memory_vectorizer.cosine_similarity(query_embedding, vec)
                scored.append((m.id, sim))
            scored.sort(key=lambda x: x[1], reverse=True)
            for rank, (mid, sim) in enumerate(scored[: limit * 2], start=1):
                semantic_results[mid] = rank
        else:
            total = keyword_w + entity_w
            if total > 0:
                keyword_w = keyword_w / total
                entity_w = entity_w / total
            semantic_w = 0.0

        try:
            fts_rows = db.execute(
                text(
                    "SELECT rowid, bm25(research_memories_fts) as rank "
                    "FROM research_memories_fts "
                    "WHERE research_memories_fts MATCH :q "
                    "ORDER BY rank LIMIT :limit"
                ),
                {"q": query, "limit": limit * 2},
            ).fetchall()
            for rank, row in enumerate(fts_rows, start=1):
                keyword_results[row[0]] = rank
        except Exception:
            pass

        try:
            matched_entities = memory_entity_engine.find_entities_in_query(db, query)
            if matched_entities:
                entity_ids = [e.id for e in matched_entities]
                entity_memory_ids = memory_entity_engine.get_entity_memory_ids(db, entity_ids)
                for rank, mid in enumerate(sorted(entity_memory_ids), start=1):
                    entity_results[mid] = rank
        except Exception:
            pass

        all_ids = set(semantic_results.keys()) | set(keyword_results.keys()) | set(entity_results.keys())
        if not all_ids:
            return []

        k = 60
        rrf_scores = {}
        channel_scores = {}
        for mid in all_ids:
            score = 0.0
            cs = {}
            if mid in semantic_results:
                part = semantic_w / (k + semantic_results[mid])
                score += part
                cs["semantic"] = part
            if mid in keyword_results:
                part = keyword_w / (k + keyword_results[mid])
                score += part
                cs["keyword"] = part
            if mid in entity_results:
                part = entity_w / (k + entity_results[mid])
                score += part
                cs["entity"] = part
            rrf_scores[mid] = score
            channel_scores[mid] = cs

        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        memories_by_id = {}
        for m in db.query(ResearchMemory).filter(
            ResearchMemory.id.in_(sorted_ids),
            ResearchMemory.is_active == True,
            ResearchMemory.confidence >= min_confidence,
        ).all():
            memories_by_id[m.id] = m

        results = []
        for mid in sorted_ids:
            if mid not in memories_by_id:
                continue
            m = memories_by_id[mid]
            if memory_types and m.memory_type not in memory_types:
                continue
            if tags:
                m_tags = _parse_tags(m.tags)
                if not any(t in m_tags for t in tags):
                    continue
            m._rrf_score = rrf_scores[mid]
            m._channel_scores = channel_scores[mid]
            results.append(m)
            if len(results) >= limit:
                break

        now = datetime.utcnow()
        for m in results:
            m.access_count += 1
            m.last_accessed_at = now
        db.commit()

        return results

    def recall_for_context(
        self,
        db: Session,
        paper_id=None,
        call_type=None,
        max_chars=1500,
    ) -> str:
        type_map = {
            "academic_reading": ["preference", "direction"],
            "critical_review": ["connection", "experience"],
            "formal_deconstruct": ["experience"],
            "smart_note": ["preference", "experience"],
            "vocabulary": [],
            "knowledge_extraction": ["preference", "direction", "connection"],
            "knowledge_query": ["preference", "experience", "direction", "connection"],
        }
        memory_types = type_map.get(
            call_type, ["preference", "experience", "direction", "connection"]
        )

        lines = []
        total_chars = 0

        obs_query = db.query(MemoryObservation)
        entity_names_for_obs = None

        if paper_id:
            paper_memories = (
                db.query(ResearchMemory)
                .filter(
                    ResearchMemory.is_active == True,
                    ResearchMemory.source_paper_id == paper_id,
                )
                .all()
            )
            paper_memory_ids = [m.id for m in paper_memories]
            if paper_memory_ids:
                try:
                    from app.models.memory_entity import MemoryEntityLink
                    links = db.query(MemoryEntityLink).filter(
                        MemoryEntityLink.memory_id.in_(paper_memory_ids)
                    ).all()
                    entity_ids = list({l.entity_id for l in links})
                    if entity_ids:
                        from app.models.memory_entity import MemoryEntity
                        entities = db.query(MemoryEntity).filter(
                            MemoryEntity.id.in_(entity_ids)
                        ).all()
                        entity_names_for_obs = [e.name for e in entities]
                except Exception:
                    pass

        if memory_types and entity_names_for_obs is None:
            try:
                from app.models.memory_entity import MemoryEntity, MemoryEntityLink
                type_memories = (
                    db.query(ResearchMemory)
                    .filter(
                        ResearchMemory.is_active == True,
                        ResearchMemory.memory_type.in_(memory_types),
                    )
                    .all()
                )
                type_memory_ids = [m.id for m in type_memories]
                if type_memory_ids:
                    links = db.query(MemoryEntityLink).filter(
                        MemoryEntityLink.memory_id.in_(type_memory_ids)
                    ).all()
                    entity_ids = list({l.entity_id for l in links})
                    if entity_ids:
                        entities = db.query(MemoryEntity).filter(
                            MemoryEntity.id.in_(entity_ids)
                        ).all()
                        entity_names_for_obs = [e.name for e in entities]
            except Exception:
                pass

        if entity_names_for_obs:
            obs_query = obs_query.filter(
                MemoryObservation.entity_name.in_(entity_names_for_obs)
            )

        observations = obs_query.order_by(MemoryObservation.proof_count.desc()).all()

        for obs in observations:
            line = f"[观察] {obs.entity_name}: {obs.content}（证据: {obs.proof_count} 条，趋势: {obs.freshness_trend}）"
            if total_chars + len(line) > max_chars:
                break
            lines.append(line)
            total_chars += len(line)

        if total_chars < max_chars:
            recall_query = " ".join(entity_names_for_obs) if entity_names_for_obs else " ".join(memory_types) if memory_types else ""
            raw_memories = self.recall(
                db,
                query=recall_query,
                memory_types=memory_types if memory_types else None,
                limit=10,
            )
            for m in raw_memories:
                line = f"- [{m.memory_type}] {m.title}: {m.content}（置信度: {m.confidence}）"
                if total_chars + len(line) > max_chars:
                    break
                lines.append(line)
                total_chars += len(line)

        return "\n".join(lines)

    def reflect(self, db: Session, query: str, entity_name: str = None) -> dict:
        from app.services.memory_reflector import memory_reflector
        return memory_reflector.reflect(db, query, entity_name)

    def forget_stale(self, db: Session, days=90, min_access_count=1) -> int:
        cutoff = datetime.utcnow() - timedelta(days=days)
        stale = (
            db.query(ResearchMemory)
            .filter(
                ResearchMemory.is_active == True,
                ResearchMemory.last_accessed_at < cutoff,
                ResearchMemory.access_count <= min_access_count,
            )
            .all()
        )
        for m in stale:
            m.is_active = False
        db.commit()
        return len(stale)

    def _supersede(self, db: Session, old_memory: ResearchMemory, new_memory: ResearchMemory) -> None:
        old_memory.is_active = False
        old_memory.superseded_by = new_memory.id

        old_tags = _parse_tags(old_memory.tags)
        new_tags = _parse_tags(new_memory.tags)
        merged = list(set(old_tags + new_tags))
        new_memory.tags = json.dumps(merged, ensure_ascii=False)

        new_memory.confidence = max(old_memory.confidence, new_memory.confidence)

        self._update_superseded_obsidian(old_memory, new_memory)

    def _sync_to_obsidian(self, memory: ResearchMemory) -> None:
        settings = get_settings()
        vault_path = Path(settings.obsidian_vault_path)
        memory_dir = vault_path / "04-科研记忆" / memory.memory_type
        memory_dir.mkdir(parents=True, exist_ok=True)

        slug = _slug(memory.title)
        file_path = memory_dir / f"{slug}.md"

        tags = _parse_tags(memory.tags)
        frontmatter = {
            "memory_id": memory.id,
            "memory_type": memory.memory_type,
            "source_type": memory.source_type,
            "confidence": memory.confidence,
            "tags": tags,
            "source_paper": memory.source_paper_id,
            "created": memory.created_at.isoformat() if memory.created_at else None,
            "updated": memory.updated_at.isoformat() if memory.updated_at else None,
        }

        yaml_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip()
        file_content = f"---\n{yaml_str}\n---\n\n{memory.content}"

        file_path.write_text(file_content, encoding="utf-8")

    def _update_superseded_obsidian(self, old_memory: ResearchMemory, new_memory: ResearchMemory) -> None:
        settings = get_settings()
        vault_path = Path(settings.obsidian_vault_path)
        old_slug = _slug(old_memory.title)
        old_file = vault_path / "04-科研记忆" / old_memory.memory_type / f"{old_slug}.md"

        if not old_file.exists():
            return

        content = old_file.read_text(encoding="utf-8")
        notice = f"\n\n> [!warning] 已被取代\n> 此记忆已被记忆 #{new_memory.id}（{new_memory.title}）取代。\n"
        content += notice
        old_file.write_text(content, encoding="utf-8")

    def get_stats(self, db: Session) -> dict:
        from sqlalchemy import func as sa_func

        by_type = (
            db.query(ResearchMemory.memory_type, sa_func.count(ResearchMemory.id))
            .group_by(ResearchMemory.memory_type)
            .all()
        )
        by_source = (
            db.query(ResearchMemory.source_type, sa_func.count(ResearchMemory.id))
            .group_by(ResearchMemory.source_type)
            .all()
        )
        by_active = (
            db.query(ResearchMemory.is_active, sa_func.count(ResearchMemory.id))
            .group_by(ResearchMemory.is_active)
            .all()
        )

        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_count = (
            db.query(ResearchMemory)
            .filter(ResearchMemory.created_at >= week_ago)
            .count()
        )

        top_recalled = (
            db.query(ResearchMemory)
            .filter(ResearchMemory.is_active == True)
            .order_by(ResearchMemory.access_count.desc())
            .limit(10)
            .all()
        )

        return {
            "by_memory_type": {row[0]: row[1] for row in by_type},
            "by_source_type": {row[0]: row[1] for row in by_source},
            "by_active_status": {str(row[0]): row[1] for row in by_active},
            "created_last_7_days": recent_count,
            "top_recalled": [
                {
                    "id": m.id,
                    "title": m.title,
                    "memory_type": m.memory_type,
                    "access_count": m.access_count,
                }
                for m in top_recalled
            ],
        }

    def list_memories(
        self,
        db: Session,
        memory_type=None,
        tags=None,
        source_type=None,
        is_active=True,
        q=None,
        limit=50,
        offset=0,
    ) -> list:
        query = db.query(ResearchMemory)

        if memory_type:
            query = query.filter(ResearchMemory.memory_type == memory_type)
        if source_type:
            query = query.filter(ResearchMemory.source_type == source_type)
        if is_active is not None:
            query = query.filter(ResearchMemory.is_active == is_active)

        if tags:
            from sqlalchemy import or_
            tag_filters = []
            for tag in tags:
                tag_filters.append(ResearchMemory.tags.contains(tag))
            query = query.filter(or_(*tag_filters))

        if q:
            try:
                fts_result = db.execute(
                    text(
                        "SELECT rowid FROM research_memories_fts WHERE research_memories_fts MATCH :q"
                    ),
                    {"q": q},
                ).fetchall()
                matching_ids = [row[0] for row in fts_result]
                query = query.filter(ResearchMemory.id.in_(matching_ids))
            except Exception:
                pass

        return (
            query.order_by(ResearchMemory.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_memory(self, db: Session, memory_id: int) -> ResearchMemory:
        return db.query(ResearchMemory).filter(ResearchMemory.id == memory_id).first()

    def update_memory(
        self,
        db: Session,
        memory_id: int,
        title=None,
        content=None,
        tags=None,
        confidence=None,
    ) -> ResearchMemory:
        memory = db.query(ResearchMemory).filter(ResearchMemory.id == memory_id).first()
        if not memory:
            return None

        if title is not None:
            memory.title = title
        if content is not None:
            memory.content = content
        if tags is not None:
            if isinstance(tags, list):
                tags = json.dumps(tags, ensure_ascii=False)
            memory.tags = tags
        if confidence is not None:
            memory.confidence = confidence

        memory.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(memory)
        self._sync_to_obsidian(memory)
        return memory

    def delete_memory(self, db: Session, memory_id: int) -> dict:
        memory = db.query(ResearchMemory).filter(ResearchMemory.id == memory_id).first()
        if not memory:
            return {"id": memory_id, "action": "not_found"}

        memory.is_active = False

        dependents = (
            db.query(ResearchMemory)
            .filter(ResearchMemory.superseded_by == memory_id)
            .all()
        )
        for dep in dependents:
            dep.superseded_by = None

        db.commit()
        return {"id": memory_id, "action": "soft_deleted"}

    def import_from_vault(self, db: Session) -> dict:
        settings = get_settings()
        vault_path = Path(settings.obsidian_vault_path)
        memory_base = vault_path / "04-科研记忆"

        if not memory_base.exists():
            return {"imported": 0, "skipped": 0}

        imported = 0
        skipped = 0

        for md_file in memory_base.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            if not content.startswith("---"):
                continue

            parts = content.split("---", 2)
            if len(parts) < 3:
                continue

            try:
                frontmatter = yaml.safe_load(parts[1])
            except yaml.YAMLError:
                continue

            if not isinstance(frontmatter, dict):
                continue

            memory_id = frontmatter.get("memory_id")
            if memory_id:
                existing = (
                    db.query(ResearchMemory)
                    .filter(ResearchMemory.id == memory_id)
                    .first()
                )
                if existing:
                    skipped += 1
                    continue

            memory_type = frontmatter.get("memory_type", "experience")
            tags = frontmatter.get("tags", [])
            confidence = frontmatter.get("confidence", 1.0)
            source_type = frontmatter.get("source_type", "user_manual")
            source_paper = frontmatter.get("source_paper")

            body = parts[2].strip()
            title = md_file.stem

            memory = ResearchMemory(
                memory_type=memory_type,
                title=title,
                content=body,
                tags=json.dumps(tags, ensure_ascii=False) if tags else None,
                source_paper_id=source_paper,
                source_type=source_type,
                confidence=confidence,
                access_count=0,
                is_active=True,
            )
            db.add(memory)
            imported += 1

        db.commit()
        return {"imported": imported, "skipped": skipped}


memory_engine = MemoryEngine()
