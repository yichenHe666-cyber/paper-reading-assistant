from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.database.session import Base


class LLMCache(Base):
    __tablename__ = "llm_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(200), nullable=False, unique=True, index=True)
    result_json = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    hit_count = Column(Integer, default=1)
    created_at = Column(String, default=func.now())
