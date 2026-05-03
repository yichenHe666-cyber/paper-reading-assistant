import json
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database.session import get_db
from app.models.research_report import ResearchReport
from app.models.paper import Paper

logger = logging.getLogger(__name__)

router = APIRouter()


class ResearchRequest(BaseModel):
    query: str
    report_type: str = "research_report"
    report_source: str = "web"
    tone: str = "Objective"
    query_domains: list[str] = None
    paper_id: str = None


class ResearchLinkRequest(BaseModel):
    research_id: str
    paper_id: str


@router.get("")
def list_reports(
    paper_id: str = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(ResearchReport).order_by(ResearchReport.created_at.desc())
    if paper_id:
        q = q.filter(ResearchReport.paper_id == paper_id)
    total = q.count()
    reports = q.offset(offset).limit(limit).all()
    return {
        "total": total,
        "reports": [_report_to_dict(r) for r in reports],
    }


@router.get("/{research_id}")
def get_report(research_id: str, db: Session = Depends(get_db)):
    report = db.query(ResearchReport).filter(ResearchReport.id == research_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="研究报告不存在")
    result = _report_to_dict(report)
    if report.paper_id:
        paper = db.query(Paper).filter(Paper.id == report.paper_id).first()
        if paper:
            result["paper"] = {"id": paper.id, "title": paper.title}
    return result


@router.post("")
def create_research(
    req: ResearchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if req.paper_id:
        paper = db.query(Paper).filter(Paper.id == req.paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="关联论文不存在")

    report = ResearchReport(
        query=req.query,
        report_type=req.report_type,
        report_source=req.report_source,
        tone=req.tone,
        paper_id=req.paper_id,
        status="pending",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    background_tasks.add_task(
        _run_research_background,
        report.id,
        req.query,
        req.report_type,
        req.report_source,
        req.tone,
        req.query_domains,
    )

    return {"id": report.id, "status": "pending", "message": "研究任务已提交，正在后台执行"}


@router.post("/sync")
def create_research_sync(req: ResearchRequest, db: Session = Depends(get_db)):
    if req.paper_id:
        paper = db.query(Paper).filter(Paper.id == req.paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="关联论文不存在")

    from app.services.research_service import run_research_sync

    result = run_research_sync(
        query=req.query,
        report_type=req.report_type,
        report_source=req.report_source,
        tone=req.tone,
        query_domains=req.query_domains,
    )

    if "error" in result:
        return {"error": result["error"], "status": "failed"}

    report = ResearchReport(
        query=req.query,
        report_type=req.report_type,
        report_source=req.report_source,
        tone=req.tone,
        paper_id=req.paper_id,
        report_content=result.get("report", ""),
        source_urls=json.dumps(result.get("source_urls", []), ensure_ascii=False),
        visited_urls=json.dumps(result.get("visited_urls", []), ensure_ascii=False),
        research_costs=result.get("costs", 0.0),
        status="completed",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return _report_to_dict(report)


@router.post("/link")
def link_to_paper(req: ResearchLinkRequest, db: Session = Depends(get_db)):
    report = db.query(ResearchReport).filter(ResearchReport.id == req.research_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="研究报告不存在")
    paper = db.query(Paper).filter(Paper.id == req.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    report.paper_id = req.paper_id
    db.commit()
    return {"success": True, "research_id": report.id, "paper_id": paper.id}


@router.delete("/{research_id}")
def delete_report(research_id: str, db: Session = Depends(get_db)):
    report = db.query(ResearchReport).filter(ResearchReport.id == research_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="研究报告不存在")
    db.delete(report)
    db.commit()
    return {"success": True}


@router.get("/paper/{paper_id}/related")
def get_paper_research(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    reports = (
        db.query(ResearchReport)
        .filter(ResearchReport.paper_id == paper_id)
        .order_by(ResearchReport.created_at.desc())
        .all()
    )
    return {"paper_id": paper_id, "title": paper.title, "reports": [_report_to_dict(r) for r in reports]}


def _report_to_dict(r: ResearchReport) -> dict:
    source_urls = []
    visited_urls = []
    try:
        if r.source_urls:
            source_urls = json.loads(r.source_urls)
    except (json.JSONDecodeError, TypeError):
        source_urls = []
    try:
        if r.visited_urls:
            visited_urls = json.loads(r.visited_urls)
    except (json.JSONDecodeError, TypeError):
        visited_urls = []

    return {
        "id": r.id,
        "query": r.query,
        "report_type": r.report_type,
        "report_source": r.report_source,
        "tone": r.tone,
        "report_content": r.report_content,
        "source_urls": source_urls,
        "visited_urls": visited_urls,
        "research_costs": r.research_costs,
        "status": r.status,
        "paper_id": r.paper_id,
        "created_at": r.created_at,
    }


def _run_research_background(
    research_id: str,
    query: str,
    report_type: str,
    report_source: str,
    tone: str,
    query_domains: list[str],
):
    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        from app.services.research_service import run_research_sync

        result = run_research_sync(
            query=query,
            report_type=report_type,
            report_source=report_source,
            tone=tone,
            query_domains=query_domains,
        )

        report = db.query(ResearchReport).filter(ResearchReport.id == research_id).first()
        if not report:
            return

        if "error" in result:
            report.status = "failed"
            report.report_content = result["error"]
        else:
            report.status = "completed"
            report.report_content = result.get("report", "")
            report.source_urls = json.dumps(result.get("source_urls", []), ensure_ascii=False)
            report.visited_urls = json.dumps(result.get("visited_urls", []), ensure_ascii=False)
            report.research_costs = result.get("costs", 0.0)

        db.commit()
    except Exception as e:
        logger.error(f"Background research failed: {e}", exc_info=True)
        report = db.query(ResearchReport).filter(ResearchReport.id == research_id).first()
        if report:
            report.status = "failed"
            report.report_content = str(e)
            db.commit()
    finally:
        db.close()
