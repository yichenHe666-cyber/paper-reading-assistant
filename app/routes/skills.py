from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.services import skill_manager
from app.services.clawhub_client import ClawHubClient, ClawHubError
from app.services.skill_executor import build_skill_prompt_segment

router = APIRouter()


@router.get("")
def list_skills(
    source: str = None,
    enabled: str = None,
    q: str = None,
    db: Session = Depends(get_db),
):
    enabled_val = None
    if enabled is not None:
        if enabled.lower() in ("true", "1", "yes"):
            enabled_val = True
        elif enabled.lower() in ("false", "0", "no"):
            enabled_val = False
    skills = skill_manager.list_skills(db, source=source, enabled=enabled_val, q=q)
    return [
        {
            "id": s.id,
            "name": s.name,
            "slug": s.slug,
            "description": s.description,
            "source": s.source,
            "enabled": s.enabled,
            "clawhub_slug": s.clawhub_slug,
            "clawhub_version": s.clawhub_version,
            "created_at": str(s.created_at),
            "updated_at": str(s.updated_at),
        }
        for s in skills
    ]


@router.get("/{skill_id}")
def get_skill(skill_id: int, db: Session = Depends(get_db)):
    skill = skill_manager.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    metadata = None
    if skill.metadata_json:
        import json
        try:
            metadata = json.loads(skill.metadata_json)
        except (json.JSONDecodeError, TypeError):
            metadata = None
    return {
        "id": skill.id,
        "name": skill.name,
        "slug": skill.slug,
        "description": skill.description,
        "source": skill.source,
        "content": skill.content,
        "enabled": skill.enabled,
        "metadata": metadata,
        "clawhub_slug": skill.clawhub_slug,
        "clawhub_version": skill.clawhub_version,
        "created_at": str(skill.created_at),
        "updated_at": str(skill.updated_at),
    }


@router.post("/import")
def import_skill(data: dict, db: Session = Depends(get_db)):
    content = data.get("content", "")
    name = data.get("name", "")
    description = data.get("description", "")
    metadata_json = data.get("metadata_json")
    overwrite = data.get("overwrite", False)

    if content and content.strip().startswith("---"):
        result = skill_manager.import_skill(db, content, overwrite=overwrite)
    elif name and description:
        result = skill_manager.import_skill_raw(
            db, name=name, description=description, content=content or description,
            metadata_json=metadata_json, overwrite=overwrite,
        )
    else:
        return {"error": "请提供完整的 SKILL.md 内容（含 YAML frontmatter），或提供 name + description + content"}

    if "error" in result:
        if result.get("conflict"):
            raise HTTPException(status_code=409, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/{skill_id}")
def delete_skill(skill_id: int, db: Session = Depends(get_db)):
    result = skill_manager.delete_skill(db, skill_id)
    if "error" in result:
        if "不可删除" in result["error"]:
            raise HTTPException(status_code=403, detail=result["error"])
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.patch("/{skill_id}/toggle")
def toggle_skill(skill_id: int, db: Session = Depends(get_db)):
    result = skill_manager.toggle_skill(db, skill_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/clawhub/search")
def clawhub_search(q: str = ""):
    if not q:
        return []
    client = ClawHubClient()
    try:
        return client.search_skills(q)
    except ClawHubError as e:
        return {"error": str(e)}


@router.post("/clawhub/install")
def clawhub_install(data: dict, db: Session = Depends(get_db)):
    slug = data.get("slug", "")
    if not slug:
        return {"error": "slug is required"}

    client = ClawHubClient()
    try:
        detail = client.download_skill(slug)
    except ClawHubError as e:
        return {"error": str(e)}

    if "error" in detail:
        return detail

    name = detail.get("name", slug)
    description = detail.get("description", "")
    content = detail.get("content", detail.get("readme", ""))
    version = detail.get("version")
    metadata = detail.get("metadata")

    if not content:
        content = f"# {name}\n\n{description}"

    result = skill_manager.install_clawhub_skill(
        db, slug=slug, name=name, description=description,
        content=content, version=version, metadata_json=metadata,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    try:
        from pathlib import Path
        skill_dir = Path("data/skills") / slug
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    except Exception:
        pass

    return result


@router.post("/clawhub/check-updates")
def clawhub_check_updates(db: Session = Depends(get_db)):
    from app.models.skill import Skill
    installed = db.query(Skill).filter(Skill.source == "clawhub").all()
    installed_data = [
        {
            "name": s.name,
            "slug": s.slug,
            "clawhub_slug": s.clawhub_slug,
            "clawhub_version": s.clawhub_version,
        }
        for s in installed
    ]
    client = ClawHubClient()
    try:
        updates = client.check_updates(installed_data)
        return updates
    except ClawHubError as e:
        return {"error": str(e)}


@router.get("/prompt-segment")
def get_skill_prompt_segment(db: Session = Depends(get_db)):
    segment = build_skill_prompt_segment(db)
    return {"segment": segment}
