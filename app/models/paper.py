from sqlalchemy import Column, String, Integer, Text, Float, DateTime, func, ForeignKey
from app.database.session import Base


class Paper(Base):
    __tablename__ = "papers"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    authors = Column(Text)
    year = Column(Integer)
    topic_id = Column(String, ForeignKey("topics.id"), nullable=False)
    subtopic = Column(String)
    venue = Column(String)
    pdf_url = Column(Text)
    doi = Column(String)
    community_notes_url = Column(Text)
    abstract = Column(Text)
    tags = Column(Text)
    difficulty = Column(String, default="中等")
    read_status = Column(String, default="未读")
    rating = Column(String)
    last_read = Column(String)
    obsidian_path = Column(String)
    obsidian_synced = Column(Integer, default=0)
    concepts = Column(Text)
    related_papers = Column(Text)
    created_at = Column(String, default=func.now())
