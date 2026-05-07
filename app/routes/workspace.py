from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.services import workspace_service

router = APIRouter()


@router.post("")
def create_workspace(data: dict, db: Session = Depends(get_db)):
    result = workspace_service.create_workspace(
        db,
        name=data.get("name", ""),
        description=data.get("description"),
        root_path=data.get("root_path"),
        icon=data.get("icon"),
        color=data.get("color"),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("")
def list_workspaces(db: Session = Depends(get_db)):
    workspaces = workspace_service.list_workspaces(db)
    result = []
    for ws in workspaces:
        stats = workspace_service.get_workspace_stats(db, ws.id)
        result.append({
            "id": ws.id,
            "name": ws.name,
            "slug": ws.slug,
            "description": ws.description,
            "root_path": ws.root_path,
            "icon": ws.icon,
            "color": ws.color,
            "is_default": ws.is_default,
            "session_count": stats["session_count"],
            "message_count": stats["message_count"],
            "created_at": str(ws.created_at),
            "updated_at": str(ws.updated_at),
        })
    return result


@router.get("/{workspace_id}")
def get_workspace(workspace_id: int, db: Session = Depends(get_db)):
    ws = workspace_service.get_workspace(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="工作空间不存在")
    stats = workspace_service.get_workspace_stats(db, ws.id)
    settings = workspace_service.get_workspace_settings(db, ws.id)
    return {
        "id": ws.id,
        "name": ws.name,
        "slug": ws.slug,
        "description": ws.description,
        "root_path": ws.root_path,
        "icon": ws.icon,
        "color": ws.color,
        "is_default": ws.is_default,
        "settings": settings,
        "stats": stats,
        "created_at": str(ws.created_at),
        "updated_at": str(ws.updated_at),
    }


@router.patch("/{workspace_id}")
def update_workspace(workspace_id: int, data: dict, db: Session = Depends(get_db)):
    ws = workspace_service.update_workspace(db, workspace_id, **data)
    if not ws:
        raise HTTPException(status_code=404, detail="工作空间不存在")
    return {"id": ws.id, "name": ws.name, "action": "updated"}


@router.delete("/{workspace_id}")
def delete_workspace(workspace_id: int, db: Session = Depends(get_db)):
    result = workspace_service.delete_workspace(db, workspace_id)
    if "error" in result:
        if "不可删除" in result["error"]:
            raise HTTPException(status_code=403, detail=result["error"])
        raise HTTPException(status_code=404, detail=result["error"])
    return result
