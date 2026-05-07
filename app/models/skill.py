from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.sql import func
from app.database.session import Base


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    source = Column(String(50), nullable=False, index=True)
    content = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(Text, nullable=True)
    clawhub_slug = Column(String(255), nullable=True)
    clawhub_version = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
