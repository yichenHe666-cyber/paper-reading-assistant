import uuid
from sqlalchemy import Column, String, Integer, Text, Float, DateTime, func, ForeignKey
from app.database.session import Base


class ResearchReport(Base):
    __tablename__ = "research_reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())[:8])
    query = Column(Text, nullable=False)
    report_type = Column(String, default="research_report")
    report_source = Column(String, default="web")
    tone = Column(String, default="Objective")
    report_content = Column(Text)
    source_urls = Column(Text)
    visited_urls = Column(Text)
    research_costs = Column(Float, default=0.0)
    quality_metrics = Column(Text)
    retriever_used = Column(String)
    search_fallback_log = Column(Text)
    status = Column(String, default="pending")
    paper_id = Column(String, ForeignKey("papers.id"), nullable=True)
    created_at = Column(String, default=func.now())
