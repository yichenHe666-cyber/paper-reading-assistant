from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database.session import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False, default="新对话")
    tags = Column(Text, nullable=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    model_name = Column(String(255), nullable=True)
    model_provider = Column(String(100), nullable=True)
    system_prompt = Column(Text, nullable=True)
    context_strategy = Column(String(20), nullable=False, default="sliding_window")
    context_max_tokens = Column(Integer, nullable=False, default=4096)
    skill_mode = Column(String(20), nullable=False, default="auto")
    enabled_skill_ids = Column(Text, nullable=True)
    enabled_rule_ids = Column(Text, nullable=True)
    total_tokens = Column(Integer, nullable=False, default=0)
    message_count = Column(Integer, nullable=False, default=0)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
