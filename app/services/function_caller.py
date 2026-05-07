import json
from sqlalchemy.orm import Session
from app.models.skill import Skill


SOURCE_PRIORITY = {"builtin": 1, "clawhub": 2, "imported": 3, "user": 4}


class FunctionCaller:

    def build_tools(self, db: Session, skill_mode: str, enabled_skill_ids: list = None) -> list:
        if skill_mode == "manual":
            skills = self._get_manual_skills(db, enabled_skill_ids or [])
        elif skill_mode == "hybrid":
            auto_skills = self._get_auto_skills(db)
            manual_skills = self._get_manual_skills(db, enabled_skill_ids or [])
            seen = set()
            skills = []
            for s in manual_skills + auto_skills:
                if s.id not in seen:
                    seen.add(s.id)
                    skills.append(s)
        else:
            skills = self._get_auto_skills(db)
        skills = self._sort_by_priority(skills, enabled_skill_ids or [])
        return [self._skill_to_tool(s) for s in skills]

    def _get_auto_skills(self, db: Session) -> list:
        return db.query(Skill).filter(Skill.enabled == True).all()

    def _get_manual_skills(self, db: Session, enabled_skill_ids: list) -> list:
        if not enabled_skill_ids:
            return []
        return db.query(Skill).filter(Skill.id.in_(enabled_skill_ids), Skill.enabled == True).all()

    def _sort_by_priority(self, skills: list, manual_ids: list) -> list:
        def priority_key(s):
            is_manual = 0 if s.id in manual_ids else 1
            source_prio = SOURCE_PRIORITY.get(s.source, 99)
            return (is_manual, source_prio, s.name)
        return sorted(skills, key=priority_key)

    def _skill_to_tool(self, skill: Skill) -> dict:
        return {
            "type": "function",
            "function": {
                "name": f"skill_{skill.slug}",
                "description": skill.description[:200],
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "用户的问题或需求",
                        }
                    },
                    "required": ["query"],
                },
            },
        }

    def resolve_tool_call(self, db: Session, function_name: str, arguments: str) -> dict:
        if not function_name.startswith("skill_"):
            return {"error": f"未知的函数调用: {function_name}"}
        slug = function_name[6:]
        skill = db.query(Skill).filter(Skill.slug == slug).first()
        if not skill:
            skill = db.query(Skill).filter(Skill.name == slug).first()
        if not skill:
            return {"error": f"技能「{slug}」不存在"}
        if not skill.enabled:
            return {"error": f"技能「{skill.name}」已禁用"}
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}
        return {
            "skill_id": skill.id,
            "skill_name": skill.name,
            "skill_slug": skill.slug,
            "skill_content": skill.content,
            "query": args.get("query", ""),
        }

    def execute_skill_call(self, db: Session, tool_call_result: dict, user_query: str) -> str:
        from app.services.skill_executor import check_skill_requirements
        skill_id = tool_call_result.get("skill_id")
        if not skill_id:
            return tool_call_result.get("error", "技能调用失败")
        skill = db.query(Skill).filter(Skill.id == skill_id).first()
        if not skill:
            return "技能不存在"
        ok, missing = check_skill_requirements(skill)
        if not ok:
            return f"技能「{skill.name}」条件不满足: {', '.join(missing)}"
        return skill.content


function_caller = FunctionCaller()
