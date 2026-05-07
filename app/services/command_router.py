import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage
from app.services.llm_utils import _call_llm
from app.config import get_settings


COMMANDS = {
    "plan": {"desc": "生成任务规划", "usage": "/plan <任务描述>"},
    "spec": {"desc": "生成需求规格", "usage": "/spec <功能描述>"},
    "skill": {"desc": "手动调用技能", "usage": "/skill <技能名称>"},
    "model": {"desc": "切换模型", "usage": "/model <模型名称>"},
    "compress": {"desc": "压缩上下文", "usage": "/compress"},
    "memory": {"desc": "查看相关记忆", "usage": "/memory"},
    "rules": {"desc": "查看当前生效规则", "usage": "/rules"},
    "workspace": {"desc": "查看工作空间信息", "usage": "/workspace"},
    "help": {"desc": "显示指令帮助", "usage": "/help"},
}


class CommandRouter:

    def route(self, db: Session, session: ChatSession, content: str) -> dict:
        parts = content.strip().split(maxsplit=1)
        cmd = parts[0][1:].lower()
        args = parts[1].strip() if len(parts) > 1 else ""
        if cmd not in COMMANDS:
            return self._create_system_message(db, session, f"未知指令: /{cmd}\n\n{self._help_text()}")
        handler = getattr(self, f"_cmd_{cmd}", None)
        if not handler:
            return self._create_system_message(db, session, f"指令 /{cmd} 尚未实现")
        return handler(db, session, args)

    def _cmd_plan(self, db: Session, session: ChatSession, args: str) -> dict:
        if not args:
            return self._create_system_message(db, session, "请提供任务描述，例如: /plan 分析这篇论文的创新点")
        prompt = f"""请为以下任务生成结构化的任务规划，包含：
1. 任务分解（子任务列表）
2. 执行顺序和依赖关系
3. 每个子任务的预期输出
4. 推荐使用的技能

任务：{args}

请以 Markdown 格式输出规划："""
        messages = [{"role": "user", "content": prompt}]
        try:
            result, usage = _call_llm(messages, max_tokens=2000)
            if isinstance(result, dict):
                result = json.dumps(result, ensure_ascii=False, indent=2)
            return self._create_assistant_message(db, session, result, usage)
        except Exception as e:
            return self._create_system_message(db, session, f"规划生成失败: {e}")

    def _cmd_spec(self, db: Session, session: ChatSession, args: str) -> dict:
        if not args:
            return self._create_system_message(db, session, "请提供功能描述，例如: /spec 论文对比分析功能")
        prompt = f"""请为以下功能生成需求规格文档，包含：
1. 功能描述
2. 用户场景
3. 输入输出规格
4. 约束条件
5. 验收标准

功能：{args}

请以 Markdown 格式输出规格文档："""
        messages = [{"role": "user", "content": prompt}]
        try:
            result, usage = _call_llm(messages, max_tokens=2000)
            if isinstance(result, dict):
                result = json.dumps(result, ensure_ascii=False, indent=2)
            return self._create_assistant_message(db, session, result, usage)
        except Exception as e:
            return self._create_system_message(db, session, f"规格生成失败: {e}")

    def _cmd_skill(self, db: Session, session: ChatSession, args: str) -> dict:
        if not args:
            from app.services.skill_manager import list_skills
            skills = list_skills(db, enabled=True)
            skill_list = "\n".join(f"- {s.name}: {s.description}" for s in skills)
            return self._create_system_message(db, session, f"可用技能:\n{skill_list}")
        from app.services.skill_executor import resolve_skill_command
        result = resolve_skill_command(db, args)
        if "error" in result:
            return self._create_system_message(db, session, result["error"])
        content = f"## 技能: {result['name']}\n\n{result.get('content', result['description'])}"
        return self._create_system_message(db, session, content)

    def _cmd_model(self, db: Session, session: ChatSession, args: str) -> dict:
        if not args:
            current = session.model_name or get_settings().llm_model
            return self._create_system_message(db, session, f"当前模型: {current}\n\n用法: /model <模型名称>")
        session.model_name = args
        db.commit()
        return self._create_system_message(db, session, f"模型已切换为: {args}")

    def _cmd_compress(self, db: Session, session: ChatSession, args: str) -> dict:
        from app.services.chat_engine import chat_engine
        result = chat_engine.compress_context(db, session.id)
        if "error" in result:
            return self._create_system_message(db, session, result["error"])
        before = result["before"]
        after = result["after"]
        return self._create_system_message(db, session, f"上下文已压缩\n压缩前: {before['total_tokens']} tokens ({before['usage_pct']}%)\n压缩后: {after['total_tokens']} tokens ({after['usage_pct']}%)")

    def _cmd_memory(self, db: Session, session: ChatSession, args: str) -> dict:
        from app.services.memory_engine import memory_engine
        memories = memory_engine.recall(db, query=args or "科研", limit=10)
        if not memories:
            return self._create_system_message(db, session, "暂无相关记忆")
        lines = []
        for m in memories:
            lines.append(f"- [{m.memory_type}] {m.title}: {m.content[:100]}（置信度: {m.confidence}）")
        return self._create_system_message(db, session, f"## 相关记忆\n\n" + "\n".join(lines))

    def _cmd_rules(self, db: Session, session: ChatSession, args: str) -> dict:
        from app.services.rule_service import list_rules
        enabled_ids = json.loads(session.enabled_rule_ids) if session.enabled_rule_ids else []
        rules = list_rules(db, enabled=True)
        if not rules:
            return self._create_system_message(db, session, "暂无生效规则")
        lines = []
        for r in rules:
            marker = "✓" if r.id in enabled_ids or r.scope == "global" else "○"
            lines.append(f"- {marker} [{r.category}] {r.name} (优先级: {r.priority})")
        return self._create_system_message(db, session, f"## 当前生效规则\n\n" + "\n".join(lines))

    def _cmd_workspace(self, db: Session, session: ChatSession, args: str) -> dict:
        if not session.workspace_id:
            return self._create_system_message(db, session, "当前会话未关联工作空间")
        from app.services.workspace_service import get_workspace, get_workspace_stats
        ws = get_workspace(db, session.workspace_id)
        if not ws:
            return self._create_system_message(db, session, "工作空间不存在")
        stats = get_workspace_stats(db, ws.id)
        return self._create_system_message(db, session, f"## 工作空间: {ws.name}\n\n- 描述: {ws.description or '无'}\n- 路径: {ws.root_path or '未设置'}\n- 会话数: {stats['session_count']}\n- 消息数: {stats['message_count']}")

    def _cmd_help(self, db: Session, session: ChatSession, args: str) -> dict:
        return self._create_system_message(db, session, self._help_text())

    def _help_text(self) -> str:
        lines = ["## 可用指令\n"]
        for cmd, info in COMMANDS.items():
            lines.append(f"- `/{cmd}` — {info['desc']}  \n  用法: `{info['usage']}`")
        return "\n".join(lines)

    def _create_system_message(self, db: Session, session: ChatSession, content: str) -> dict:
        msg = ChatMessage(
            session_id=session.id,
            role="system",
            content=content,
            token_count=len(content) // 4,
        )
        db.add(msg)
        session.message_count += 1
        session.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(msg)
        return {"message_id": msg.id, "content": content, "role": "system"}

    def _create_assistant_message(self, db: Session, session: ChatSession, content: str, usage: dict) -> dict:
        msg = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=content,
            token_count=usage.get("completion_tokens", 0),
            model_used=session.model_name or get_settings().llm_model,
        )
        db.add(msg)
        session.message_count += 1
        session.total_tokens += usage.get("total_tokens", 0)
        session.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(msg)
        return {"message_id": msg.id, "content": content, "usage": usage, "role": "assistant"}


command_router = CommandRouter()
