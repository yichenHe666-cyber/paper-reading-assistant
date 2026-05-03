from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.database.session import Base


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(20), nullable=False)
    component = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    paper_id = Column(String)
    created_at = Column(String, default=func.now())
