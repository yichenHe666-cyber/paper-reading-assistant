from sqlalchemy import Column, String, Integer, Text, Float, DateTime, func
from app.database.session import Base


class Topic(Base):
    __tablename__ = "topics"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    name_cn = Column(String)
    description = Column(Text)
    paper_count = Column(Integer, default=0)
    icon = Column(String, default="📄")
    fa_icon = Column(String, default="file-lines")
    created_at = Column(String, default=func.now())
