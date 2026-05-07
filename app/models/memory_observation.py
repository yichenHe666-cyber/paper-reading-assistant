from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from sqlalchemy.sql import func
from app.database.session import Base


class MemoryObservation(Base):
    __tablename__ = "memory_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_name = Column(String(200), nullable=False, index=True)
    content = Column(Text, nullable=False)
    source_memory_ids = Column(Text, nullable=False)
    evidence_quotes = Column(Text, nullable=True)
    proof_count = Column(Integer, default=0)
    freshness_trend = Column(String(20), default="stable")
    confidence = Column(Float, default=0.8)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
