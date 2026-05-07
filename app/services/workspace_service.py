import re
import json
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.workspace import Workspace
from app.config import get_settings


def _slug(text: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"\s+", "-", safe).strip("-")[:60]


def list_workspaces(db: Session) -> list:
    return db.query(Workspace).order_by(Workspace.is_default.desc(), Workspace.name.asc()).all()


def get_workspace(db: Session, workspace_id: int) -> Workspace:
    return db.query(Workspace).filter(Workspace.id == workspace_id).first()


def create_workspace(db: Session, name: str, description: str = None, root_path: str = None, icon: str = None, color: str = None) -> dict:
    slug = _slug(name)
    existing = db.query(Workspace).filter(Workspace.slug == slug).first()
    if existing:
        return {"error": f"工作空间「{name}」已存在"}
    ws = Workspace(name=name, slug=slug, description=description, root_path=root_path, icon=icon, color=color)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    _create_vault_directory(ws)
    return {"id": ws.id, "name": ws.name, "slug": ws.slug}


def update_workspace(db: Session, workspace_id: int, **kwargs) -> Workspace:
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        return None
    for key, value in kwargs.items():
        if hasattr(ws, key) and value is not None:
            setattr(ws, key, value)
    db.commit()
    db.refresh(ws)
    return ws


def delete_workspace(db: Session, workspace_id: int) -> dict:
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        return {"error": "工作空间不存在"}
    if ws.is_default:
        return {"error": "默认工作空间不可删除"}
    from app.models.chat_session import ChatSession
    sessions = db.query(ChatSession).filter(ChatSession.workspace_id == workspace_id).all()
    for s in sessions:
        s.workspace_id = None
    db.delete(ws)
    db.commit()
    return {"id": workspace_id, "action": "deleted"}


def get_workspace_stats(db: Session, workspace_id: int) -> dict:
    from app.models.chat_session import ChatSession
    from app.models.chat_message import ChatMessage
    from sqlalchemy import func as sa_func
    session_count = db.query(ChatSession).filter(ChatSession.workspace_id == workspace_id).count()
    session_ids = [s.id for s in db.query(ChatSession).filter(ChatSession.workspace_id == workspace_id).all()]
    message_count = db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).count() if session_ids else 0
    return {"session_count": session_count, "message_count": message_count}


def get_workspace_settings(db: Session, workspace_id: int) -> dict:
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws or not ws.settings_json:
        return {}
    try:
        return json.loads(ws.settings_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def _create_vault_directory(ws: Workspace) -> None:
    try:
        settings = get_settings()
        vault_path = Path(settings.obsidian_vault_path)
        ws_dir = vault_path / "工作空间" / ws.slug
        ws_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
