import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database.session import get_db
from app.models.paper import Paper
from app.models.topic import Topic
from app.models import ReadingHistory

router = APIRouter()


@router.get("")
def list_papers(
    topic_id: str = None,
    status: str = None,
    difficulty: str = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(Paper)
    if topic_id:
        q = q.filter(Paper.topic_id == topic_id)
    if status:
        q = q.filter(Paper.read_status == status)
    if difficulty:
        q = q.filter(Paper.difficulty == difficulty)

    total = q.count()
    papers = q.order_by(Paper.year.desc().nullslast()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "papers": [
            {
                "id": p.id,
                "title": p.title,
                "authors": p.authors,
                "year": p.year,
                "topic_id": p.topic_id,
                "subtopic": p.subtopic,
                "venue": p.venue,
                "pdf_url": p.pdf_url,
                "community_notes_url": p.community_notes_url,
                "abstract": p.abstract,
                "tags": p.tags,
                "difficulty": p.difficulty,
                "read_status": p.read_status,
                "rating": p.rating,
                "last_read": p.last_read,
                "obsidian_path": p.obsidian_path,
                "obsidian_synced": bool(p.obsidian_synced),
                "concepts": p.concepts,
                "related_papers": p.related_papers,
                "created_at": str(p.created_at) if p.created_at else None,
            }
            for p in papers
        ],
    }


@router.get("/search")
def search_papers(q: str, limit: int = 20, db: Session = Depends(get_db)):
    from app.services.fts_manager import search_papers_fts
    return search_papers_fts(q, limit)


@router.get("/{paper_id:path}")
def get_paper(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        return {"error": "论文不存在"}
    topic = db.query(Topic).filter(Topic.id == paper.topic_id).first()
    return {
        "id": paper.id,
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "topic_id": paper.topic_id,
        "topic_name": topic.name if topic else "",
        "topic_name_cn": topic.name_cn if topic else "",
        "subtopic": paper.subtopic,
        "venue": paper.venue,
        "pdf_url": paper.pdf_url,
        "community_notes_url": paper.community_notes_url,
        "abstract": paper.abstract,
        "tags": paper.tags,
        "difficulty": paper.difficulty,
        "read_status": paper.read_status,
        "rating": paper.rating,
        "last_read": paper.last_read,
        "obsidian_path": paper.obsidian_path,
        "obsidian_synced": bool(paper.obsidian_synced),
        "concepts": paper.concepts,
        "related_papers": paper.related_papers,
        "created_at": str(paper.created_at) if paper.created_at else None,
    }


@router.patch("/{paper_id:path}")
def update_paper(paper_id: str, updates: dict, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        return {"error": "论文不存在"}
    old_read_status = paper.read_status
    for key in ["read_status", "rating", "difficulty", "last_read", "tags", "obsidian_path"]:
        if key in updates:
            setattr(paper, key, updates[key])
    if "obsidian_synced" in updates:
        paper.obsidian_synced = 1 if updates["obsidian_synced"] else 0

    new_read_status = updates.get("read_status", None)
    if new_read_status and new_read_status != old_read_status:
        now = datetime.now().isoformat()
        if new_read_status == "精读中":
            history = ReadingHistory(
                paper_id=paper_id,
                started_at=now,
                status="reading",
            )
            db.add(history)
            logging.getLogger("paper_reader").info(f"[papers] {paper_id}: started reading")
        elif new_read_status in ("已读", "重读"):
            latest = db.query(ReadingHistory).filter(
                ReadingHistory.paper_id == paper_id,
                ReadingHistory.status == "reading",
                ReadingHistory.ended_at == None,
            ).order_by(ReadingHistory.id.desc()).first()
            if latest:
                started = datetime.fromisoformat(latest.started_at) if latest.started_at else datetime.now()
                duration = int((datetime.now() - started).total_seconds())
                latest.ended_at = now
                latest.duration_seconds = duration
                latest.status = "completed"
                db.add(latest)
                logging.getLogger("paper_reader").info(f"[papers] {paper_id}: completed reading ({duration}s)")

    if "progress" in updates:
        now = datetime.now().isoformat()
        latest = db.query(ReadingHistory).filter(
            ReadingHistory.paper_id == paper_id,
            ReadingHistory.status == "reading",
        ).order_by(ReadingHistory.id.desc()).first()
        if latest:
            import json as json_lib
            current = json_lib.loads(latest.progress_json or "{}")
            current.update(updates["progress"])
            current["updated_at"] = now
            latest.progress_json = json_lib.dumps(current, ensure_ascii=False)
            db.add(latest)

    db.commit()
    return {"status": "ok"}


@router.post("/{paper_id:path}/favorite")
def toggle_favorite(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        return {"error": "论文不存在"}
    if paper.read_status == "已读":
        paper.read_status = "重读"
    else:
        paper.read_status = "已读"
    db.commit()
    return {"status": "ok", "read_status": paper.read_status}
