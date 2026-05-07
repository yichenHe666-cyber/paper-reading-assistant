from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func as sa_func, or_, text
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.services.memory_engine import memory_engine
from app.services.memory_entity_engine import memory_entity_engine
from app.models.memory_entity import MemoryEntity, MemoryEntityLink
from app.models.memory_observation import MemoryObservation
from app.services.memory_observer import memory_observer
from app.services.memory_vectorizer import memory_vectorizer
from app.models.research_memory import ResearchMemory
from app.models.paper import Paper
from app.models.reading_history import ReadingHistory
from app.services.llm_cache import get_cache

router = APIRouter()


def _serialize_memory(m):
    return {
        "id": m.id,
        "memory_type": m.memory_type,
        "title": m.title,
        "content": m.content,
        "tags": m.tags,
        "source_type": m.source_type,
        "confidence": m.confidence,
        "access_count": m.access_count,
        "is_active": m.is_active,
        "superseded_by": m.superseded_by,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


@router.get("")
def list_memories(
    memory_type: str = None,
    tags: str = None,
    source_type: str = None,
    is_active: bool = True,
    q: str = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    memories = memory_engine.list_memories(
        db,
        memory_type=memory_type,
        tags=tag_list,
        source_type=source_type,
        is_active=is_active,
        q=q,
        limit=limit,
        offset=offset,
    )

    count_q = db.query(sa_func.count(ResearchMemory.id))
    if memory_type:
        count_q = count_q.filter(ResearchMemory.memory_type == memory_type)
    if source_type:
        count_q = count_q.filter(ResearchMemory.source_type == source_type)
    if is_active is not None:
        count_q = count_q.filter(ResearchMemory.is_active == is_active)
    if tag_list:
        tag_filters = [ResearchMemory.tags.contains(tag) for tag in tag_list]
        count_q = count_q.filter(or_(*tag_filters))
    if q:
        try:
            fts_result = db.execute(
                text("SELECT rowid FROM research_memories_fts WHERE research_memories_fts MATCH :q"),
                {"q": q},
            ).fetchall()
            matching_ids = [row[0] for row in fts_result]
            count_q = count_q.filter(ResearchMemory.id.in_(matching_ids))
        except Exception:
            pass

    total = count_q.scalar()

    return {
        "memories": [_serialize_memory(m) for m in memories],
        "total": total,
    }


@router.post("", status_code=201)
def create_memory(data: dict, db: Session = Depends(get_db)):
    memory_type = data.get("memory_type")
    title = data.get("title")
    content = data.get("content")
    if not memory_type or not title or not content:
        raise HTTPException(status_code=400, detail="memory_type, title, content 为必填项")

    tags = data.get("tags", [])
    source_paper_id = data.get("source_paper_id")
    confidence = data.get("confidence", 1.0)

    memory = memory_engine.remember(
        db,
        memory_type=memory_type,
        title=title,
        content=content,
        tags=tags,
        source_paper_id=source_paper_id,
        source_type="user_manual",
        confidence=confidence,
    )
    return _serialize_memory(memory)


@router.get("/search")
def search_memories(
    q: str,
    memory_types: str = None,
    db: Session = Depends(get_db),
):
    types_list = None
    if memory_types:
        types_list = [t.strip() for t in memory_types.split(",") if t.strip()]
    memories = memory_engine.recall(db, query=q, memory_types=types_list)
    return {
        "memories": [_serialize_memory(m) for m in memories],
        "query": q,
    }


@router.get("/stats")
def memory_stats(db: Session = Depends(get_db)):
    return memory_engine.get_stats(db)


@router.post("/distill/{paper_id}")
def distill_paper(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    reading_history = (
        db.query(ReadingHistory)
        .filter(ReadingHistory.paper_id == paper_id)
        .order_by(ReadingHistory.id.desc())
        .first()
    )

    call_types = ["学术阅读引擎", "形式化拆解", "批判性审查", "智能笔记合成"]
    cached = {}
    for ct in call_types:
        result = get_cache(db, paper_id, ct)
        if result:
            cached[ct] = result

    reading_result = {
        "paper": {
            "id": paper.id,
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
        },
    }
    if reading_history:
        reading_result["reading_history"] = {
            "status": reading_history.status,
            "rating": reading_history.rating,
            "progress_json": reading_history.progress_json,
        }
    if cached:
        reading_result["llm_outputs"] = cached

    if not cached and not reading_history:
        raise HTTPException(status_code=400, detail="论文阅读数据不足，无法蒸馏")

    from app.services.memory_distiller import memory_distiller
    result = memory_distiller.distill_reading_session(paper_id, reading_result)

    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    memories_created = result.get("memories_created", 0) if isinstance(result, dict) else 0
    return {"status": "ok", "memories_created": memories_created}


@router.post("/reflect")
def reflect_memories(data: dict, db: Session = Depends(get_db)):
    query = data.get("query", "")
    entity_name = data.get("entity_name")
    if not query:
        raise HTTPException(status_code=400, detail="query 为必填项")
    result = memory_engine.reflect(db, query=query, entity_name=entity_name)
    save = data.get("save_as_memory", False)
    if save:
        from app.services.memory_reflector import memory_reflector
        memory = memory_reflector.save_reflection_as_memory(db, result, query, entity_name)
        if memory:
            result["saved_memory_id"] = memory.id
    return result


@router.get("/observations")
def list_observations(
    entity_name: str = None,
    freshness_trend: str = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(MemoryObservation)
    if entity_name:
        q = q.filter(MemoryObservation.entity_name.contains(entity_name))
    if freshness_trend:
        q = q.filter(MemoryObservation.freshness_trend == freshness_trend)
    total = q.count()
    observations = q.order_by(MemoryObservation.updated_at.desc()).offset(offset).limit(limit).all()
    return {
        "observations": [
            {
                "id": o.id,
                "entity_name": o.entity_name,
                "content": o.content,
                "source_memory_ids": o.source_memory_ids,
                "evidence_quotes": o.evidence_quotes,
                "proof_count": o.proof_count,
                "freshness_trend": o.freshness_trend,
                "confidence": o.confidence,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            }
            for o in observations
        ],
        "total": total,
    }


@router.post("/observations/consolidate")
def consolidate_observations(data: dict = None, db: Session = Depends(get_db)):
    entity_name = None
    if data:
        entity_name = data.get("entity_name")
    if entity_name:
        result = memory_observer.consolidate_entity(db, entity_name)
        if result:
            return {"status": "ok", "observation_id": result.id, "entity_name": result.entity_name}
        return {"status": "skipped", "reason": "not enough memories or consolidation failed"}
    else:
        result = memory_observer.run_consolidation_cycle(db)
        return {"status": "ok", "consolidated": result.get("consolidated", 0), "failed": result.get("failed", 0)}


@router.get("/entities")
def list_entities(
    entity_type: str = None,
    q: str = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(MemoryEntity)
    if entity_type:
        query = query.filter(MemoryEntity.entity_type == entity_type)
    if q:
        query = query.filter(MemoryEntity.name.contains(q))
    total = query.count()
    entities = query.order_by(MemoryEntity.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "entity_type": e.entity_type,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "memory_count": db.query(MemoryEntityLink).filter(MemoryEntityLink.entity_id == e.id).count(),
            }
            for e in entities
        ],
        "total": total,
    }


@router.get("/entities/{entity_id}/memories")
def get_entity_memories(entity_id: int, db: Session = Depends(get_db)):
    entity = db.query(MemoryEntity).filter(MemoryEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="实体不存在")
    memories = memory_entity_engine.find_memories_by_entity(db, entity.name)
    return {
        "entity": {"id": entity.id, "name": entity.name, "entity_type": entity.entity_type},
        "memories": [_serialize_memory(m) for m in memories],
    }


@router.post("/backfill-embeddings")
def backfill_embeddings(db: Session = Depends(get_db)):
    result = memory_vectorizer.backfill_embeddings(db)
    return {"status": "ok", "processed": result.get("processed", 0), "failed": result.get("failed", 0)}


@router.get("/{memory_id}")
def get_memory(memory_id: int, db: Session = Depends(get_db)):
    memory = memory_engine.get_memory(db, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")

    result = _serialize_memory(memory)
    if memory.superseded_by:
        superseding = db.query(ResearchMemory).filter(ResearchMemory.id == memory.superseded_by).first()
        if superseding:
            result["superseded_chain"] = {
                "id": superseding.id,
                "title": superseding.title,
            }
    return result


@router.put("/{memory_id}")
def update_memory(memory_id: int, data: dict, db: Session = Depends(get_db)):
    memory = memory_engine.update_memory(
        db,
        memory_id=memory_id,
        title=data.get("title"),
        content=data.get("content"),
        tags=data.get("tags"),
        confidence=data.get("confidence"),
    )
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return _serialize_memory(memory)


@router.delete("/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    result = memory_engine.delete_memory(db, memory_id)
    if result.get("action") == "not_found":
        raise HTTPException(status_code=404, detail="记忆不存在")
    return result
