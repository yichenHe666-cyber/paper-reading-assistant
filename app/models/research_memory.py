from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey, LargeBinary
from sqlalchemy.sql import func
from app.database.session import Base


class ResearchMemory(Base):
    __tablename__ = "research_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_type = Column(String(20), nullable=False, index=True)
    content = Column(Text, nullable=False)
    title = Column(String(100), nullable=False)
    tags = Column(Text, nullable=True)
    source_paper_id = Column(Integer, ForeignKey("papers.id"), nullable=True)
    source_type = Column(String(20), nullable=False, index=True)
    confidence = Column(Float, default=1.0, nullable=False)
    access_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    superseded_by = Column(Integer, ForeignKey("research_memories.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    last_accessed_at = Column(DateTime, nullable=True)
    embedding = Column(LargeBinary, nullable=True)
    embedding_model = Column(String(50), nullable=True)
    observation_id = Column(Integer, ForeignKey("memory_observations.id"), nullable=True)
