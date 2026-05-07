from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database.session import Base


class SandboxRecord(Base):
    __tablename__ = "sandbox_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    operation_type = Column(String(20), nullable=False)
    input_data = Column(Text, nullable=True)
    output_data = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    permissions_used = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
