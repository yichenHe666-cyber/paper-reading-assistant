from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.services import rule_service

router = APIRouter()


@router.post("")
def create_rule(data: dict, db: Session = Depends(get_db)):
    result = rule_service.create_rule(
        db,
        name=data.get("name", ""),
        description=data.get("description", ""),
        content=data.get("content", ""),
        category=data.get("category", "custom"),
        priority=data.get("priority", 50),
        scope=data.get("scope", "global"),
        conflict_resolution=data.get("conflict_resolution", "highest_priority"),
        workspace_id=data.get("workspace_id"),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("")
def list_rules(
    category: str = None,
    enabled: str = None,
    scope: str = None,
    q: str = None,
    db: Session = Depends(get_db),
):
    enabled_val = None
    if enabled is not None:
        if enabled.lower() in ("true", "1", "yes"):
            enabled_val = True
        elif enabled.lower() in ("false", "0", "no"):
            enabled_val = False
    rules = rule_service.list_rules(db, category=category, enabled=enabled_val, scope=scope, q=q)
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "category": r.category,
            "priority": r.priority,
            "enabled": r.enabled,
            "source": r.source,
            "scope": r.scope,
            "workspace_id": r.workspace_id,
            "conflict_resolution": r.conflict_resolution,
            "created_at": str(r.created_at),
            "updated_at": str(r.updated_at),
        }
        for r in rules
    ]


@router.get("/{rule_id}")
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = rule_service.get_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "content": rule.content,
        "category": rule.category,
        "priority": rule.priority,
        "enabled": rule.enabled,
        "source": rule.source,
        "scope": rule.scope,
        "workspace_id": rule.workspace_id,
        "conflict_resolution": rule.conflict_resolution,
        "created_at": str(rule.created_at),
        "updated_at": str(rule.updated_at),
    }


@router.put("/{rule_id}")
def update_rule(rule_id: int, data: dict, db: Session = Depends(get_db)):
    rule = rule_service.update_rule(db, rule_id, **data)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"id": rule.id, "name": rule.name, "action": "updated"}


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    result = rule_service.delete_rule(db, rule_id)
    if "error" in result:
        if "不可删除" in result["error"]:
            raise HTTPException(status_code=403, detail=result["error"])
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.patch("/{rule_id}/toggle")
def toggle_rule(rule_id: int, db: Session = Depends(get_db)):
    result = rule_service.toggle_rule(db, rule_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/import")
def import_rules(data: dict, db: Session = Depends(get_db)):
    rules_data = data.get("rules", [])
    overwrite = data.get("overwrite", False)
    if not rules_data:
        raise HTTPException(status_code=400, detail="rules 不能为空")
    result = rule_service.import_rules(db, rules_data, overwrite=overwrite)
    return result


@router.get("/export")
def export_rules(rule_ids: str = None, db: Session = Depends(get_db)):
    ids = None
    if rule_ids:
        try:
            ids = [int(x) for x in rule_ids.split(",")]
        except ValueError:
            pass
    return rule_service.export_rules(db, rule_ids=ids)
