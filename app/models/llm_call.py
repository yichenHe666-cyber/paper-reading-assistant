from sqlalchemy import Column, Integer, String, Float, Text, DateTime, func
from app.database.session import Base


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_type = Column(String, nullable=False)
    model = Column(String, nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    cost_usd = Column(Float, nullable=False)
    duration_ms = Column(Integer, default=0)
    paper_id = Column(String)
    created_at = Column(String, default=func.now())
