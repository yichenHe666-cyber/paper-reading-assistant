from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, LargeBinary
from sqlalchemy.sql import func
from app.database.session import Base


class MemoryEntity(Base):
    __tablename__ = "memory_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True)
    entity_type = Column(String(30), nullable=False)
    embedding = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class MemoryEntityLink(Base):
    __tablename__ = "memory_entity_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(Integer, ForeignKey("research_memories.id"), nullable=False)
    entity_id = Column(Integer, ForeignKey("memory_entities.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
