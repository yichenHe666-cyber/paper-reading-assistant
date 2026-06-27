import json
import re
from sqlalchemy.orm import Session
from app.models.agent_rule import AgentRule
from app.services.skill_manager import check_safety


BUILTIN_RULE_NAMES = {"academic-rigor", "chinese-response", "safety-guard"}


def list_rules(db: Session, category: str = None, enabled: bool = None, scope: str = None, q: str = None) -> list:
    query = db.query(AgentRule)
    if category:
        query = query.filter(AgentRule.category == category)
    if enabled is not None:
        query = query.filter(AgentRule.enabled == enabled)
    if scope:
        query = query.filter(AgentRule.scope == scope)
    if q:
        query = query.filter(AgentRule.name.contains(q))
    return query.order_by(AgentRule.priority.desc(), AgentRule.name.asc()).all()


def get_rule(db: Session, rule_id: int) -> AgentRule:
    return db.query(AgentRule).filter(AgentRule.id == rule_id).first()


def create_rule(db: Session, name: str, description: str, content: str, category: str, priority: int = 50, scope: str = "global", conflict_resolution: str = "highest_priority", workspace_id: int = None) -> dict:
    existing = db.query(AgentRule).filter(AgentRule.name == name).first()
    if existing:
        return {"error": f"规则「{name}」已存在"}
    safe, danger = check_safety(content)
    if not safe:
        return {"error": f"规则内容包含不安全的代码模式（{danger}），已拒绝创建"}
    rule = AgentRule(
        name=name, description=description, content=content,
        category=category, priority=priority, enabled=True,
        source="user", scope=scope, workspace_id=workspace_id,
        conflict_resolution=conflict_resolution,
    )
    db.add(rule)
    db.commit()
    return {"id": rule.id, "name": rule.name}


RULE_UPDATEABLE_FIELDS = {
    "name", "description", "content", "category", "priority",
    "enabled", "scope", "workspace_id", "conflict_resolution", "metadata_json",
}


def update_rule(db: Session, rule_id: int, **kwargs) -> AgentRule:
    rule = db.query(AgentRule).filter(AgentRule.id == rule_id).first()
    if not rule:
        return None
    for key, value in kwargs.items():
        if key in RULE_UPDATEABLE_FIELDS:
            setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, rule_id: int) -> dict:
    rule = db.query(AgentRule).filter(AgentRule.id == rule_id).first()
    if not rule:
        return {"error": "规则不存在"}
    if rule.source == "builtin":
        return {"error": "内置规则不可删除"}
    db.delete(rule)
    db.commit()
    return {"id": rule_id, "action": "deleted"}


def toggle_rule(db: Session, rule_id: int) -> dict:
    rule = db.query(AgentRule).filter(AgentRule.id == rule_id).first()
    if not rule:
        return {"error": "规则不存在"}
    rule.enabled = not rule.enabled
    db.commit()
    return {"id": rule.id, "name": rule.name, "enabled": rule.enabled}


def build_rule_prompt_segment(db: Session, enabled_rule_ids: list = None, workspace_id: int = None, max_chars: int = 2000) -> str:
    rules = db.query(AgentRule).filter(AgentRule.enabled == True, AgentRule.scope == "global").all()
    if workspace_id:
        ws_rules = db.query(AgentRule).filter(AgentRule.enabled == True, AgentRule.scope == "workspace", AgentRule.workspace_id == workspace_id).all()
        rules = list(rules) + list(ws_rules)
    if enabled_rule_ids:
        session_rules = db.query(AgentRule).filter(AgentRule.id.in_(enabled_rule_ids), AgentRule.enabled == True).all()
        seen = {r.id for r in rules}
        for r in session_rules:
            if r.id not in seen:
                rules.append(r)
    rules.sort(key=lambda r: r.priority, reverse=True)
    lines = []
    total = 0
    for rule in rules:
        line = f"- [{rule.category}] {rule.name}: {rule.description}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines) if lines else ""


def resolve_conflicts(rules: list) -> list:
    name_groups = {}
    for rule in rules:
        key = (rule.category, rule.scope)
        if key not in name_groups:
            name_groups[key] = []
        name_groups[key].append(rule)
    result = []
    for key, group in name_groups.items():
        if len(group) == 1:
            result.extend(group)
            continue
        group.sort(key=lambda r: r.priority, reverse=True)
        first = group[0]
        if first.conflict_resolution == "highest_priority":
            result.append(first)
        elif first.conflict_resolution == "latest":
            result.append(max(group, key=lambda r: r.created_at or ""))
        elif first.conflict_resolution == "merge":
            merged_content = "\n".join(r.content for r in group)
            first.content = merged_content
            result.append(first)
        else:
            result.append(first)
    return result


def export_rules(db: Session, rule_ids: list = None) -> list:
    if rule_ids:
        rules = db.query(AgentRule).filter(AgentRule.id.in_(rule_ids)).all()
    else:
        rules = db.query(AgentRule).all()
    return [
        {
            "name": r.name,
            "description": r.description,
            "content": r.content,
            "category": r.category,
            "priority": r.priority,
            "scope": r.scope,
            "conflict_resolution": r.conflict_resolution,
        }
        for r in rules
    ]


def import_rules(db: Session, rules_data: list, overwrite: bool = False) -> dict:
    imported = 0
    skipped = 0
    errors = []
    for rd in rules_data:
        name = rd.get("name", "")
        if not name:
            errors.append("规则缺少 name 字段")
            continue
        safe, danger = check_safety(rd.get("content", ""))
        if not safe:
            errors.append(f"规则「{name}」包含不安全代码模式（{danger}）")
            continue
        existing = db.query(AgentRule).filter(AgentRule.name == name).first()
        if existing:
            if not overwrite:
                skipped += 1
                continue
            existing.description = rd.get("description", existing.description)
            existing.content = rd.get("content", existing.content)
            existing.category = rd.get("category", existing.category)
            existing.priority = rd.get("priority", existing.priority)
            existing.scope = rd.get("scope", existing.scope)
            existing.conflict_resolution = rd.get("conflict_resolution", existing.conflict_resolution)
        else:
            rule = AgentRule(
                name=name,
                description=rd.get("description", ""),
                content=rd.get("content", ""),
                category=rd.get("category", "custom"),
                priority=rd.get("priority", 50),
                enabled=True,
                source="imported",
                scope=rd.get("scope", "global"),
                conflict_resolution=rd.get("conflict_resolution", "highest_priority"),
            )
            db.add(rule)
        imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}
