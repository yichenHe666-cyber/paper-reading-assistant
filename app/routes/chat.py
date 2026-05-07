import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage
from app.services.chat_engine import chat_engine
from app.config import get_settings

router = APIRouter()


@router.post("/sessions")
def create_session(data: dict, db: Session = Depends(get_db)):
    settings = get_settings()
    title = data.get("title", "新对话")
    workspace_id = data.get("workspace_id")
    tags = data.get("tags", [])
    model_name = data.get("model_name") or settings.llm_model
    model_provider = data.get("model_provider") or settings.llm_provider
    session = ChatSession(
        title=title,
        workspace_id=workspace_id,
        tags=json.dumps(tags, ensure_ascii=False) if tags else None,
        model_name=model_name,
        model_provider=model_provider,
        context_max_tokens=settings.chat_default_context_max_tokens,
        context_strategy=settings.chat_default_context_strategy,
        skill_mode=settings.chat_default_skill_mode,
    )
    if workspace_id:
        from app.services.workspace_service import get_workspace_settings
        ws_settings = get_workspace_settings(db, workspace_id)
        if ws_settings:
            if "model_name" in ws_settings and not data.get("model_name"):
                session.model_name = ws_settings["model_name"]
            if "skill_mode" in ws_settings and not data.get("skill_mode"):
                session.skill_mode = ws_settings["skill_mode"]
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_to_dict(session)


@router.get("/sessions")
def list_sessions(
    workspace_id: int = None,
    q: str = None,
    is_archived: str = "false",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(ChatSession)
    if workspace_id:
        query = query.filter(ChatSession.workspace_id == workspace_id)
    if is_archived.lower() in ("false", "0", "no"):
        query = query.filter(ChatSession.is_archived == False)
    elif is_archived.lower() in ("true", "1", "yes"):
        query = query.filter(ChatSession.is_archived == True)
    if q:
        try:
            from sqlalchemy import text
            fts_result = db.execute(
                text("SELECT DISTINCT session_id FROM chat_messages_fts WHERE chat_messages_fts MATCH :q"),
                {"q": q},
            ).fetchall()
            matching_ids = [row[0] for row in fts_result]
            query = query.filter(ChatSession.id.in_(matching_ids))
        except Exception:
            query = query.filter(ChatSession.title.contains(q))
    total = query.count()
    sessions = query.order_by(ChatSession.updated_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "sessions": [_session_to_dict(s) for s in sessions]}


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(50)
        .all()
    )
    messages.reverse()
    result = _session_to_dict(session)
    result["messages"] = [_message_to_dict(m) for m in messages]
    return result


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, data: dict, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    updatable = ["title", "model_name", "model_provider", "system_prompt", "context_strategy", "context_max_tokens", "skill_mode", "is_archived"]
    for key in updatable:
        if key in data:
            setattr(session, key, data[key])
    if "tags" in data:
        session.tags = json.dumps(data["tags"], ensure_ascii=False)
    if "enabled_skill_ids" in data:
        session.enabled_skill_ids = json.dumps(data["enabled_skill_ids"], ensure_ascii=False)
    if "enabled_rule_ids" in data:
        session.enabled_rule_ids = json.dumps(data["enabled_rule_ids"], ensure_ascii=False)
    db.commit()
    db.refresh(session)
    return _session_to_dict(session)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete(session)
    db.commit()
    return {"id": session_id, "action": "deleted"}


@router.post("/sessions/{session_id}/messages")
def send_message(session_id: int, data: dict, db: Session = Depends(get_db)):
    content = data.get("content", "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    result = chat_engine.send_message(db, session_id, content, stream=False)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/sessions/{session_id}/messages/stream")
def send_message_stream(session_id: int, data: dict, db: Session = Depends(get_db)):
    content = data.get("content", "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    def event_generator():
        for chunk in chat_engine.send_message(db, session_id, content, stream=True):
            if isinstance(chunk, str):
                yield f"data: {json.dumps({'token': chunk}, ensure_ascii=False)}\n\n"
            elif isinstance(chunk, tuple) and chunk[0] == "__usage__":
                usage_data = chunk[1]
                reasoning = usage_data.get("reasoning_content", "")
                event = {"usage": {k: v for k, v in usage_data.items() if k != "reasoning_content"}}
                if reasoning:
                    event["reasoning_content"] = reasoning
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/sessions/{session_id}/messages")
def get_messages(
    session_id: int,
    limit: int = 50,
    before_id: int = None,
    db: Session = Depends(get_db),
):
    query = db.query(ChatMessage).filter(ChatMessage.session_id == session_id)
    if before_id:
        query = query.filter(ChatMessage.id < before_id)
    messages = query.order_by(ChatMessage.created_at.desc()).limit(limit).all()
    messages.reverse()
    return {"messages": [_message_to_dict(m) for m in messages]}


@router.post("/sessions/{session_id}/compress")
def compress_context(session_id: int, db: Session = Depends(get_db)):
    result = chat_engine.compress_context(db, session_id)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/sessions/{session_id}/context-usage")
def get_context_usage(session_id: int, db: Session = Depends(get_db)):
    result = chat_engine.get_context_usage(db, session_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/sessions/{session_id}/export")
def export_session(session_id: int, format: str = "markdown", db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    if format == "json":
        return {
            "session": _session_to_dict(session),
            "messages": [_message_to_dict(m) for m in messages],
        }
    lines = [f"# {session.title}", ""]
    for m in messages:
        role_label = {"user": "用户", "assistant": "助手", "system": "系统", "function_call": "技能调用", "function_result": "技能结果"}.get(m.role, m.role)
        lines.append(f"**[{role_label}]** ({m.created_at}):")
        lines.append(m.content)
        lines.append("")
    return {"content": "\n".join(lines), "format": "markdown"}


def _session_to_dict(session: ChatSession) -> dict:
    tags = None
    if session.tags:
        try:
            tags = json.loads(session.tags)
        except (json.JSONDecodeError, TypeError):
            tags = []
    enabled_skill_ids = None
    if session.enabled_skill_ids:
        try:
            enabled_skill_ids = json.loads(session.enabled_skill_ids)
        except (json.JSONDecodeError, TypeError):
            enabled_skill_ids = []
    enabled_rule_ids = None
    if session.enabled_rule_ids:
        try:
            enabled_rule_ids = json.loads(session.enabled_rule_ids)
        except (json.JSONDecodeError, TypeError):
            enabled_rule_ids = []
    return {
        "id": session.id,
        "title": session.title,
        "tags": tags,
        "workspace_id": session.workspace_id,
        "model_name": session.model_name,
        "model_provider": session.model_provider,
        "system_prompt": session.system_prompt,
        "context_strategy": session.context_strategy,
        "context_max_tokens": session.context_max_tokens,
        "skill_mode": session.skill_mode,
        "enabled_skill_ids": enabled_skill_ids,
        "enabled_rule_ids": enabled_rule_ids,
        "total_tokens": session.total_tokens,
        "message_count": session.message_count,
        "is_archived": session.is_archived,
        "created_at": str(session.created_at),
        "updated_at": str(session.updated_at),
    }


def _message_to_dict(msg: ChatMessage) -> dict:
    skill_calls = None
    if msg.skill_calls:
        try:
            skill_calls = json.loads(msg.skill_calls)
        except (json.JSONDecodeError, TypeError):
            skill_calls = None
    return {
        "id": msg.id,
        "session_id": msg.session_id,
        "role": msg.role,
        "content": msg.content,
        "reasoning_content": msg.reasoning_content,
        "skill_calls": skill_calls,
        "token_count": msg.token_count,
        "model_used": msg.model_used,
        "context_usage_pct": msg.context_usage_pct,
        "created_at": str(msg.created_at),
    }
