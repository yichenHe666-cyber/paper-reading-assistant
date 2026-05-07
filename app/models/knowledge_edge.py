from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database.session import Base


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_concept = Column(String, nullable=False)
    target_concept = Column(String, nullable=False)
    relation_type = Column(String, nullable=False)
    strength = Column(Float, default=0.5)
    evidence = Column(Text)
    source_document_id = Column(Integer, ForeignKey("knowledge_documents.id"))
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
