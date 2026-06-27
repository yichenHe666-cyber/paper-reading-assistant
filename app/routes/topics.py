from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.session import get_db
from app.models.topic import Topic
from app.models.paper import Paper
from app.services.github_fetcher import sync_all_papers, TOPIC_ICONS

router = APIRouter()


def _get_fa_icon(topic_id: str) -> str:
    """Get Font Awesome icon class for a topic."""
    return TOPIC_ICONS.get(topic_id, "file-lines")


@router.get("")
def list_topics(db: Session = Depends(get_db)):
    topics = db.query(Topic).all()
    paper_counts = dict(
        db.query(Paper.topic_id, func.count(Paper.id))
        .group_by(Paper.topic_id)
        .all()
    )
    return [
        {
            "id": t.id,
            "name": t.name,
            "name_cn": t.name_cn,
            "icon": t.icon,
            "fa_icon": t.fa_icon or _get_fa_icon(t.id),
            "paper_count": paper_counts.get(t.id, 0),
            "description": t.description,
        }
        for t in topics
    ]


@router.get("/uncategorized")
def uncategorized_topics(db: Session = Depends(get_db)):
    all_topics = db.query(Topic).all()
    paper_counts = dict(
        db.query(Paper.topic_id, func.count(Paper.id))
        .group_by(Paper.topic_id)
        .all()
    )
    empty = []
    for t in all_topics:
        count = paper_counts.get(t.id, 0)
        if count == 0:
            empty.append({
                "id": t.id,
                "name": t.name,
                "name_cn": t.name_cn,
                "icon": t.icon,
                "fa_icon": t.fa_icon or _get_fa_icon(t.id),
            })
    total_papers = db.query(func.count(Paper.id)).scalar()
    total_topics = len(all_topics)
    topics_with_papers = total_topics - len(empty)
    return {
        "total_papers": total_papers,
        "total_topics": total_topics,
        "topics_with_papers": topics_with_papers,
        "empty_topics_count": len(empty),
        "empty_topics": empty,
    }


@router.get("/{topic_id}")
def get_topic(topic_id: str, db: Session = Depends(get_db)):
    from app.models.paper import Paper
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="主题不存在")
    papers = db.query(Paper).filter(Paper.topic_id == topic_id).all()
    return {
        "id": topic.id,
        "name": topic.name,
        "name_cn": topic.name_cn,
        "icon": topic.icon,
        "fa_icon": topic.fa_icon or _get_fa_icon(topic.id),
        "paper_count": len(papers),
        "papers": [
            {
                "id": p.id,
                "title": p.title,
                "authors": p.authors,
                "year": p.year,
                "difficulty": p.difficulty,
                "read_status": p.read_status,
                "obsidian_synced": bool(p.obsidian_synced),
            }
            for p in papers
        ],
    }


@router.post("/fetch")
def fetch_topics(force: bool = Query(False), db: Session = Depends(get_db)):
    try:
        result = sync_all_papers(db, force=force)
        return {"status": "ok", **result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
