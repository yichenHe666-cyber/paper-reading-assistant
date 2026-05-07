from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database.session import Base


class AgentRule(Base):
    __tablename__ = "agent_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(20), nullable=False, index=True)
    priority = Column(Integer, nullable=False, default=50)
    enabled = Column(Boolean, nullable=False, default=True)
    source = Column(String(20), nullable=False)
    scope = Column(String(20), nullable=False, default="global")
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    conflict_resolution = Column(String(20), nullable=False, default="highest_priority")
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
