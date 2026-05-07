import json
import os
from sqlalchemy.orm import Session
from app.models.skill import Skill
from app.config import get_settings


SOURCE_PRIORITY = {"builtin": 0, "clawhub": 1, "imported": 2}


def get_enabled_skills(db: Session) -> list[Skill]:
    return db.query(Skill).filter(Skill.enabled == True).all()


def build_skill_prompt_segment(db: Session) -> str:
    skills = get_enabled_skills(db)
    if not skills:
        return ""

    settings = get_settings()
    max_chars = int(settings.llm_max_tokens * 0.3 * 4)

    sorted_skills = sorted(skills, key=lambda s: SOURCE_PRIORITY.get(s.source, 99))

    segments = []
    total_len = 0
    for skill in sorted_skills:
        segment = f'<skill name="{skill.name}">{skill.description}</skill>'
        if total_len + len(segment) > max_chars:
            break
        segments.append(segment)
        total_len += len(segment)

    if not segments:
        return ""

    return "\n".join(segments)


def resolve_skill_command(db: Session, command: str) -> dict:
    command = command.strip()
    if command.startswith("/skill "):
        name = command[7:].strip()
    else:
        name = command.strip()

    skill = db.query(Skill).filter(Skill.name == name).first()
    if not skill:
        skill = db.query(Skill).filter(Skill.slug == name).first()
    if not skill:
        return {"error": f"技能「{name}」不存在"}

    if not skill.enabled:
        return {"error": f"技能「{name}」已禁用"}

    return {"name": skill.name, "description": skill.description, "content": skill.content}


def check_skill_requirements(skill: Skill) -> tuple[bool, list[str]]:
    if not skill.metadata_json:
        return True, []

    try:
        meta = json.loads(skill.metadata_json)
    except (json.JSONDecodeError, TypeError):
        return True, []

    openclaw_meta = meta.get("openclaw", {})
    requires = openclaw_meta.get("requires", {})

    missing = []
    for env_var in requires.get("env", []):
        if not os.getenv(env_var):
            missing.append(f"环境变量 {env_var}")

    for bin_name in requires.get("bins", []):
        from shutil import which
        if not which(bin_name):
            missing.append(f"可执行文件 {bin_name}")

    return len(missing) == 0, missing
