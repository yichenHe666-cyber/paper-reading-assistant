# -*- coding: utf-8 -*-
"""Data quality monitoring service for paper metadata."""
import sqlite3
from datetime import datetime
from pathlib import Path
from app.database.session import SessionLocal
from app.models.paper import Paper
from app.models.topic import Topic


def get_quality_metrics() -> dict:
    """Return current data quality metrics for papers."""
    db = SessionLocal()
    try:
        total = db.query(Paper).count()
        if total == 0:
            return {"total_papers": 0, "status": "no_data"}

        missing_authors = db.query(Paper).filter(
            (Paper.authors.is_(None)) |
            (Paper.authors == "") |
            (Paper.authors == "[]") |
            (Paper.authors == '["Unknown"]')
        ).count()

        missing_year = db.query(Paper).filter(Paper.year.is_(None)).count()

        missing_pdf = db.query(Paper).filter(
            (Paper.pdf_url.is_(None)) | (Paper.pdf_url == "")
        ).count()

        missing_abstract = db.query(Paper).filter(
            (Paper.abstract.is_(None)) | (Paper.abstract == "")
        ).count()

        # Per-topic breakdown for authors
        topic_breakdown = []
        topics = db.query(Topic).all()
        for t in topics:
            t_total = db.query(Paper).filter(Paper.topic_id == t.id).count()
            if t_total == 0:
                continue
            t_missing_authors = db.query(Paper).filter(
                Paper.topic_id == t.id,
                (Paper.authors.is_(None)) |
                (Paper.authors == "") |
                (Paper.authors == "[]") |
                (Paper.authors == '["Unknown"]')
            ).count()
            t_missing_year = db.query(Paper).filter(
                Paper.topic_id == t.id,
                Paper.year.is_(None)
            ).count()
            topic_breakdown.append({
                "topic_id": t.id,
                "topic_name": t.name_cn or t.name,
                "total": t_total,
                "missing_authors": t_missing_authors,
                "missing_authors_pct": round(t_missing_authors / t_total * 100, 1),
                "missing_year": t_missing_year,
                "missing_year_pct": round(t_missing_year / t_total * 100, 1),
            })

        # Sort by missing percentage desc
        topic_breakdown.sort(key=lambda x: x["missing_authors_pct"], reverse=True)

        return {
            "total_papers": total,
            "missing_authors": missing_authors,
            "missing_authors_pct": round(missing_authors / total * 100, 1),
            "missing_year": missing_year,
            "missing_year_pct": round(missing_year / total * 100, 1),
            "missing_pdf": missing_pdf,
            "missing_abstract": missing_abstract,
            "healthy": missing_authors_pct < 30 and missing_year_pct < 30,
            "checked_at": datetime.now().isoformat(),
            "topic_breakdown": topic_breakdown[:10],
        }
    finally:
        db.close()


def log_quality_snapshot():
    """Persist a quality snapshot to the database for trend tracking."""
    db = SessionLocal()
    try:
        metrics = get_quality_metrics()
        # Store in system_log for simplicity
        from app.models.system_log import SystemLog
        log = SystemLog(
            level="INFO",
            component="data_quality",
            message=f"Data quality check: {metrics['missing_authors_pct']}% missing authors, {metrics['missing_year_pct']}% missing year",
            paper_id=None,
        )
        db.add(log)
        db.commit()
    finally:
        db.close()


def check_sync_quality(expected_new: int, expected_updated: int) -> dict:
    """Run after sync to validate data quality."""
    metrics = get_quality_metrics()
    issues = []

    if metrics["missing_authors_pct"] > 50:
        issues.append(f"作者缺失率过高: {metrics['missing_authors_pct']}%")
    if metrics["missing_year_pct"] > 50:
        issues.append(f"年份缺失率过高: {metrics['missing_year_pct']}%")
    if metrics["missing_pdf"] > 0:
        issues.append(f"有 {metrics['missing_pdf']} 篇论文缺少 PDF 链接")

    return {
        "metrics": metrics,
        "issues": issues,
        "pass": len(issues) == 0,
    }
