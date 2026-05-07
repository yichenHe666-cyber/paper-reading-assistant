import json
import time
from sqlalchemy.orm import Session
from app.models.sandbox_record import SandboxRecord
from app.config import get_settings


DEFAULT_PERMISSIONS = ["read_filesystem", "web_search", "llm_call"]
DENIED_PERMISSIONS = ["write_filesystem", "system_command", "env_modify"]


def execute_in_sandbox(db: Session, operation_type: str, input_data: dict, session_id: int = None, workspace_id: int = None, extra_permissions: list = None) -> dict:
    settings = get_settings()
    record = SandboxRecord(
        session_id=session_id,
        workspace_id=workspace_id,
        operation_type=operation_type,
        input_data=json.dumps(input_data, ensure_ascii=False),
        status="running",
        permissions_used=json.dumps(DEFAULT_PERMISSIONS + (extra_permissions or []), ensure_ascii=False),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    start_time = time.time()
    try:
        for perm in (extra_permissions or []):
            if perm in DENIED_PERMISSIONS:
                raise PermissionError(f"权限「{perm}」被禁止")
        result = _execute_operation(db, operation_type, input_data)
        duration = int((time.time() - start_time) * 1000)
        record.output_data = json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        record.status = "success"
        record.duration_ms = duration
        db.commit()
        return {"record_id": record.id, "status": "success", "result": result, "duration_ms": duration}
    except Exception as e:
        duration = int((time.time() - start_time) * 1000)
        record.status = "failed"
        record.error_message = str(e)
        record.duration_ms = duration
        db.commit()
        return {"record_id": record.id, "status": "failed", "error": str(e), "duration_ms": duration}


def _execute_operation(db: Session, operation_type: str, input_data: dict) -> dict:
    if operation_type == "skill_test":
        return _test_skill(db, input_data)
    elif operation_type == "code_exec":
        return {"output": "代码执行功能暂未实现", "note": "沙盒代码执行需额外安全配置"}
    elif operation_type == "tool_call":
        return _test_tool(db, input_data)
    else:
        raise ValueError(f"未知的操作类型: {operation_type}")


def _test_skill(db: Session, input_data: dict) -> dict:
    from app.models.skill import Skill
    skill_id = input_data.get("skill_id")
    query = input_data.get("query", "")
    if not skill_id:
        return {"error": "缺少 skill_id"}
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return {"error": f"技能 ID {skill_id} 不存在"}
    return {"skill_name": skill.name, "skill_content_preview": skill.content[:500], "query": query, "note": "技能内容已加载，可在对话中测试"}


def _test_tool(db: Session, input_data: dict) -> dict:
    tool_name = input_data.get("tool_name", "")
    return {"tool_name": tool_name, "status": "simulated", "note": "工具调用测试完成"}


def list_records(db: Session, session_id: int = None, operation_type: str = None, status: str = None, limit: int = 50) -> list:
    q = db.query(SandboxRecord)
    if session_id:
        q = q.filter(SandboxRecord.session_id == session_id)
    if operation_type:
        q = q.filter(SandboxRecord.operation_type == operation_type)
    if status:
        q = q.filter(SandboxRecord.status == status)
    return q.order_by(SandboxRecord.created_at.desc()).limit(limit).all()


def get_record(db: Session, record_id: int) -> SandboxRecord:
    return db.query(SandboxRecord).filter(SandboxRecord.id == record_id).first()
