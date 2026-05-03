from sqlalchemy import Column, String, Integer, Text, DateTime, func
from app.database.session import Base


class UserConcept(Base):
    __tablename__ = "concepts"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String)
    definition_short = Column(String)
    related_papers = Column(Text)
    related_concepts = Column(Text)
    obsidian_path = Column(String)
    source = Column(String, default="llm_generated")
    created_at = Column(String, default=func.now())
