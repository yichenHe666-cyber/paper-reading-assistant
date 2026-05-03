from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.database.session import Base


class NoteSnapshot(Base):
    __tablename__ = "note_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String, nullable=False)
    obsidian_path = Column(String)
    content = Column(Text, nullable=False)
    version = Column(Integer, nullable=False)
    created_at = Column(String, default=func.now())
