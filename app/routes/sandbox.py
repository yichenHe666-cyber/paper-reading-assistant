from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.services import sandbox_service

router = APIRouter()


@router.post("/execute")
def execute_sandbox(data: dict, db: Session = Depends(get_db)):
    operation_type = data.get("operation_type", "")
    input_data = data.get("input_data", {})
    session_id = data.get("session_id")
    workspace_id = data.get("workspace_id")
    extra_permissions = data.get("extra_permissions", [])
    if not operation_type:
        raise HTTPException(status_code=400, detail="operation_type 不能为空")
    result = sandbox_service.execute_in_sandbox(
        db,
        operation_type=operation_type,
        input_data=input_data,
        session_id=session_id,
        workspace_id=workspace_id,
        extra_permissions=extra_permissions,
    )
    return result


@router.get("/records")
def list_records(
    session_id: int = None,
    operation_type: str = None,
    status: str = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    records = sandbox_service.list_records(db, session_id=session_id, operation_type=operation_type, status=status, limit=limit)
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "workspace_id": r.workspace_id,
            "operation_type": r.operation_type,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "created_at": str(r.created_at),
        }
        for r in records
    ]


@router.get("/records/{record_id}")
def get_record(record_id: int, db: Session = Depends(get_db)):
    record = sandbox_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {
        "id": record.id,
        "session_id": record.session_id,
        "workspace_id": record.workspace_id,
        "operation_type": record.operation_type,
        "input_data": record.input_data,
        "output_data": record.output_data,
        "status": record.status,
        "error_message": record.error_message,
        "duration_ms": record.duration_ms,
        "permissions_used": record.permissions_used,
        "created_at": str(record.created_at),
    }
