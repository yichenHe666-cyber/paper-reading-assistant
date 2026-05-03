from sqlalchemy import Column, Integer, String, Float, DateTime, func, Text
from app.database.session import Base


class ReadingHistory(Base):
    __tablename__ = "reading_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String, nullable=False)
    started_at = Column(String)
    ended_at = Column(String)
    duration_seconds = Column(Integer)
    rating = Column(Integer)
    status = Column(String, default="reading")
    progress_json = Column(Text)
    created_at = Column(String, default=func.now())
