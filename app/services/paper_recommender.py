from sqlalchemy.orm import Session
from app.models.paper import Paper
from app.models.reading_history import ReadingHistory
from app.models.topic import Topic


def recommend_next_paper(db: Session, current_paper_id: str = None, topic_id: str = None) -> dict:
    history = db.query(ReadingHistory).filter(
        ReadingHistory.status == "completed"
    ).order_by(ReadingHistory.id.desc()).limit(30).all()

    read_ids = set()
    difficulties_read = {"简单": 0, "中等": 0, "困难": 0, "硬核": 0}
    topics_interested = {}

    for h in history:
        read_ids.add(h.paper_id)
        paper = db.query(Paper).filter(Paper.id == h.paper_id).first()
        if paper:
            diff = paper.difficulty or "中等"
            difficulties_read[diff] = difficulties_read.get(diff, 0) + 1
            topics_interested[paper.topic_id] = topics_interested.get(paper.topic_id, 0) + 1

    total_read = sum(difficulties_read.values())
    if total_read == 0:
        q = db.query(Paper).filter(Paper.read_status == "未读")
        if topic_id:
            q = q.filter(Paper.topic_id == topic_id)
        paper = q.order_by(Paper.year.desc()).first()
        if paper:
            return _paper_dict(paper) | {"reason": "这是你的第一篇论文，从最新的开始吧！"}
        return {"message": "没有更多未读论文"}

    if difficulties_read.get("简单", 0) >= 3:
        target_difficulty = "中等"
    elif difficulties_read.get("中等", 0) >= 5:
        target_difficulty = "困难"
    elif difficulties_read.get("困难", 0) >= 3:
        target_difficulty = "硬核"
    else:
        target_difficulty = "简单"

    top_topic = max(topics_interested, key=topics_interested.get) if topics_interested else None

    q = db.query(Paper).filter(~Paper.id.in_(read_ids) if read_ids else True)
    q = q.filter(Paper.read_status == "未读")
    if current_paper_id:
        q = q.filter(Paper.id != current_paper_id)

    paper = q.filter(Paper.difficulty == target_difficulty).first()
    if not paper and top_topic:
        paper = q.filter(Paper.topic_id == top_topic).first()
    if not paper:
        paper = q.order_by(Paper.year.desc()).first()

    if paper:
        reason = f"你已经读了 {total_read} 篇论文，试试{target_difficulty}难度的吧！"
        if top_topic:
            topic_name = db.query(Topic).filter(Topic.id == top_topic).first()
            if topic_name:
                reason += f" 你对「{topic_name.name_cn or topic_name.name}」似乎很感兴趣。"
        return _paper_dict(paper) | {"reason": reason}

    return {"message": "太厉害了，所有论文都读完了！"}


def recommend_by_confusion(db: Session, limit: int = 3) -> list:
    notes_dir = (db.observable if False else None)
    results = []

    try:
        papers_with_concepts = db.query(Paper).filter(Paper.concepts.isnot(None)).limit(50).all()
        concept_counts = {}
        for p in papers_with_concepts:
            import json as json_lib
            try:
                concepts = json_lib.loads(p.concepts) if p.concepts else []
            except (json_lib.JSONDecodeError, TypeError):
                concepts = []
            for c in concepts:
                concept_counts[c] = concept_counts.get(c, 0) + 1

        unread_with_concepts = [p for p in papers_with_concepts if p.read_status == "未读"]
        for p in unread_with_concepts[:limit]:
            results.append(_paper_dict(p) | {"reason": "补充理解相关概念"})
    except Exception:
        pass

    return results if results else []


def _paper_dict(paper: Paper) -> dict:
    return {
        "id": paper.id, "title": paper.title, "authors": paper.authors,
        "year": paper.year, "topic_id": paper.topic_id, "difficulty": paper.difficulty,
        "read_status": paper.read_status, "abstract": (paper.abstract or "")[:200],
    }
