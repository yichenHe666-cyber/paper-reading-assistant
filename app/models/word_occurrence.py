from sqlalchemy import Column, Integer, String, DateTime, func, UniqueConstraint
from app.database.session import Base


class WordOccurrence(Base):
    __tablename__ = "word_occurrences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word = Column(String, nullable=False)
    word_type = Column(String, nullable=False, default="cs_term")
    paper_id = Column(String, nullable=False)
    occurrence_count = Column(Integer, default=1)
    created_at = Column(String, default=func.now())

    __table_args__ = (
        UniqueConstraint("word", "paper_id", name="uq_word_paper"),
    )
