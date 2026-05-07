from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database.session import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False, unique=True)
    file_format = Column(String, nullable=False)
    file_size_bytes = Column(Integer)
    content_hash = Column(String)
    category = Column(String)
    tags = Column(Text)
    authors = Column(Text, nullable=True)
    language = Column(String, default="zh")
    page_count = Column(Integer)
    section_count = Column(Integer)
    parse_status = Column(String, default="pending")
    parse_errors = Column(Text)
    wiki_status = Column(String, default="pending")
    knowledge_extracted = Column(Boolean, default=False)
    source_type = Column(String, default="upload")
    source_url = Column(Text, nullable=True)
    related_paper_id = Column(String, ForeignKey("papers.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
