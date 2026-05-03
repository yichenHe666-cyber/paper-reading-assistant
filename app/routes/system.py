from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timedelta
from app.database.session import get_db
from app.services.cost_tracker import get_today_cost
from app.services.backup import auto_backup_db, export_all_to_zip
from app.models.cost_log import LLMCostLog
from app.models.llm_call import LLMCall
from app.models.paper import Paper
from app.models.topic import Topic
from app.models.system_log import SystemLog
from app.models.reading_history import ReadingHistory

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "经典论文精读助手"}


@router.get("/llm-cost")
def llm_cost_summary(db: Session = Depends(get_db)):
    today_str = str(date.today())
    today_llm = db.query(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).filter(
        LLMCall.created_at.like(f"{today_str}%")
    ).scalar()
    today_old = get_today_cost(db)
    total_llm = db.query(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).scalar()
    total_old = db.query(func.coalesce(func.sum(LLMCostLog.cost_usd), 0.0)).scalar()

    week_ago = str(date.today() - timedelta(days=7))
    week_llm = db.query(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).filter(
        LLMCall.created_at >= week_ago
    ).scalar()

    monthly_llm = db.query(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).filter(
        LLMCall.created_at >= str(date.today().replace(day=1))
    ).scalar()

    return {
        "today_cost_usd": round(float(today_llm) + float(today_old), 6),
        "week_cost_usd": round(float(week_llm), 6),
        "monthly_cost_usd": round(float(monthly_llm), 6),
        "total_cost_usd": round(float(total_llm) + float(total_old), 6),
    }


@router.get("/llm-cost/detail")
def llm_cost_detail(db: Session = Depends(get_db), limit: int = 50):
    calls = db.query(LLMCall).order_by(LLMCall.id.desc()).limit(limit).all()
    results = []

    today_str = str(date.today())
    for c in calls:
        results.append({
            "source": "llm_calls",
            "id": c.id,
            "call_type": c.call_type,
            "model": c.model,
            "cost_usd": c.cost_usd,
            "total_tokens": c.total_tokens,
            "duration_ms": c.duration_ms,
            "paper_id": c.paper_id,
            "created_at": str(c.created_at),
        })

    remaining = limit - len(results)
    if remaining > 0:
        old_logs = db.query(LLMCostLog).order_by(LLMCostLog.id.desc()).limit(remaining).all()
        for l in old_logs:
            results.append({
                "source": "llm_cost_log",
                "id": l.id,
                "call_type": l.call_type,
                "model": l.model,
                "cost_usd": l.cost_usd,
                "total_tokens": l.total_tokens,
                "duration_ms": 0,
                "paper_id": l.paper_id,
                "created_at": str(l.created_at),
            })

    results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return results[:limit]


@router.get("/llm-cost/daily")
def llm_cost_daily(db: Session = Depends(get_db), days: int = 14):
    start_date = str(date.today() - timedelta(days=days))
    rows = (
        db.query(
            func.substr(LLMCall.created_at, 1, 10).label("day"),
            func.coalesce(func.sum(LLMCall.cost_usd), 0.0).label("cost"),
            func.count(LLMCall.id).label("call_count"),
        )
        .filter(LLMCall.created_at >= start_date)
        .group_by("day")
        .order_by("day")
        .all()
    )
    return [{"date": r.day, "cost_usd": round(float(r.cost), 6), "calls": r.call_count} for r in rows]


@router.get("/llm-cost/by-type")
def llm_cost_by_type(db: Session = Depends(get_db), days: int = 30):
    start_date = str(date.today() - timedelta(days=days))
    rows = (
        db.query(
            LLMCall.call_type,
            func.coalesce(func.sum(LLMCall.cost_usd), 0.0).label("cost"),
            func.count(LLMCall.id).label("count"),
        )
        .filter(LLMCall.created_at >= start_date)
        .group_by(LLMCall.call_type)
        .all()
    )
    return [{"type": r.call_type, "cost_usd": round(float(r.cost), 6), "calls": r.count} for r in rows]


@router.get("/logs")
def query_logs(
    component: str = None,
    level: str = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(SystemLog).order_by(SystemLog.id.desc())
    if component:
        q = q.filter(SystemLog.component == component)
    if level:
        q = q.filter(SystemLog.level == level)
    logs = q.limit(limit).all()
    return [
        {
            "id": l.id,
            "level": l.level,
            "component": l.component,
            "message": l.message,
            "paper_id": l.paper_id,
            "created_at": str(l.created_at),
        }
        for l in logs
    ]


@router.get("/reading-stats")
def reading_stats_detail(db: Session = Depends(get_db)):
    total_papers = db.query(func.count(Paper.id)).scalar()
    unread = db.query(func.count(Paper.id)).filter(Paper.read_status == "未读").scalar()
    reading = db.query(func.count(Paper.id)).filter(Paper.read_status == "精读中").scalar()
    read = db.query(func.count(Paper.id)).filter(Paper.read_status == "已读").scalar()
    reread = db.query(func.count(Paper.id)).filter(Paper.read_status == "重读").scalar()
    total_topics = db.query(func.count(Topic.id)).scalar()
    synced = db.query(func.count(Paper.id)).filter(Paper.obsidian_synced == 1).scalar()

    completed = db.query(func.count(ReadingHistory.id)).filter(
        ReadingHistory.status == "completed"
    ).scalar()

    total_seconds = db.query(func.coalesce(func.sum(ReadingHistory.duration_seconds), 0)).filter(
        ReadingHistory.status == "completed"
    ).scalar()

    this_month = str(date.today().replace(day=1))
    month_completed = db.query(func.count(ReadingHistory.id)).filter(
        ReadingHistory.status == "completed",
        ReadingHistory.ended_at >= this_month,
    ).scalar()
    month_seconds = db.query(func.coalesce(func.sum(ReadingHistory.duration_seconds), 0)).filter(
        ReadingHistory.status == "completed",
        ReadingHistory.ended_at >= this_month,
    ).scalar()

    topic_stats = (
        db.query(Paper.topic_id, func.count(Paper.id).label("cnt"))
        .filter(Paper.read_status.in_(["已读", "重读"]))
        .group_by(Paper.topic_id)
        .order_by(func.count(Paper.id).desc())
        .limit(10)
        .all()
    )

    return {
        "total_papers": total_papers,
        "unread": unread,
        "reading": reading,
        "read": read,
        "reread": reread,
        "total_topics": total_topics,
        "synced_to_obsidian": synced,
        "reading_history": {
            "total_completed": completed,
            "total_seconds": int(total_seconds),
            "total_hours": round(float(total_seconds) / 3600, 1),
            "month_completed": month_completed,
            "month_seconds": int(month_seconds),
            "month_hours": round(float(month_seconds) / 3600, 1),
        },
        "topic_distribution": [
            {"topic_id": t.topic_id, "read_count": t.cnt} for t in topic_stats
        ],
    }


@router.get("/stats")
def reading_stats(db: Session = Depends(get_db)):
    total_papers = db.query(func.count(Paper.id)).scalar()
    unread = db.query(func.count(Paper.id)).filter(Paper.read_status == "未读").scalar()
    reading = db.query(func.count(Paper.id)).filter(Paper.read_status == "精读中").scalar()
    read = db.query(func.count(Paper.id)).filter(Paper.read_status == "已读").scalar()
    reread = db.query(func.count(Paper.id)).filter(Paper.read_status == "重读").scalar()
    total_topics = db.query(func.count(Topic.id)).scalar()
    synced = db.query(func.count(Paper.id)).filter(Paper.obsidian_synced == 1).scalar()

    return {
        "total_papers": total_papers,
        "unread": unread,
        "reading": reading,
        "read": read,
        "reread": reread,
        "total_topics": total_topics,
        "synced_to_obsidian": synced,
    }


@router.get("/backup")
def backup_database():
    try:
        path = auto_backup_db()
        return {"status": "ok", "path": path}
    except Exception as e:
        return {"error": str(e)}


@router.post("/export")
def export_all():
    try:
        path = export_all_to_zip()
        return {"status": "ok", "path": path}
    except Exception as e:
        return {"error": str(e)}


@router.get("/data-quality")
def data_quality():
    from app.services.data_quality import get_quality_metrics
    return get_quality_metrics()
