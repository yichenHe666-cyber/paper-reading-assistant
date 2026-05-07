import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage
from app.services.context_manager import context_manager
from app.services.function_caller import function_caller
from app.services.rule_service import build_rule_prompt_segment
from app.services.memory_engine import memory_engine
from app.services.knowledge_engine import knowledge_engine
from app.services.llm_utils import _call_llm, _call_llm_stream, _call_llm_with_tools, _get_model_config
from app.config import get_settings


class ChatEngine:

    def send_message(self, db: Session, session_id: int, content: str, stream: bool = False):
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            return {"error": "会话不存在"}
        user_msg = ChatMessage(
            session_id=session_id,
            role="user",
            content=content,
            token_count=len(content) // 4,
        )
        db.add(user_msg)
        session.message_count += 1
        session.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user_msg)
        if content.startswith("/"):
            from app.services.command_router import command_router
            return command_router.route(db, session, content)
        context_messages = context_manager.build_context_window(
            db, session_id, session.context_max_tokens, session.context_strategy
        )
        llm_messages = self._build_llm_messages(db, session, context_messages, content)
        api_base, api_key = _get_model_config(session.model_provider, session.model_name)
        if session.skill_mode in ("auto", "hybrid"):
            enabled_ids = json.loads(session.enabled_skill_ids) if session.enabled_skill_ids else []
            tools = function_caller.build_tools(db, session.skill_mode, enabled_ids)
            if tools:
                return self._send_with_tools(db, session, llm_messages, tools, api_base, api_key, stream)
        if stream:
            return self._send_stream(db, session, llm_messages, api_base, api_key)
        return self._send_normal(db, session, llm_messages, api_base, api_key)

    def _build_llm_messages(self, db: Session, session: ChatSession, context_messages: list, user_content: str) -> list:
        messages = []
        system_parts = []
        system_parts.append("你是「核动力科研牛马」，一位严谨的学术研究助手。你擅长论文精读、形式化拆解、批判性审查和智能笔记合成。")
        if session.system_prompt:
            system_parts.append(session.system_prompt)
        memory_segment = memory_engine.recall_for_context(db, call_type="academic_reading")
        if memory_segment:
            system_parts.append(f"## 相关记忆（仅供参考，优先相信论文原文）\n{memory_segment}\n优先相信论文原文和数学推导，记忆可能过时或不适用于当前论文。")
        knowledge_triggers = ["根据我的资料", "我之前整理的", "知识库中", "我的知识库", "我整理的"]
        enhanced = any(t in user_content for t in knowledge_triggers)
        knowledge_segment = knowledge_engine.query_for_context(user_content, enhanced=enhanced)
        if knowledge_segment:
            system_parts.append(f"## 知识库参考（基于已学习的文档）\n{knowledge_segment}\n注意：以上知识来自个人知识库，可能存在偏差，请结合上下文判断。")
        enabled_rule_ids = json.loads(session.enabled_rule_ids) if session.enabled_rule_ids else []
        rule_segment = build_rule_prompt_segment(db, enabled_rule_ids, session.workspace_id)
        if rule_segment:
            system_parts.append(f"## 行为规则\n{rule_segment}")
        enabled_skill_ids = json.loads(session.enabled_skill_ids) if session.enabled_skill_ids else []
        from app.services.skill_executor import build_skill_prompt_segment
        skill_segment = build_skill_prompt_segment(db)
        if skill_segment:
            system_parts.append(f"## 可用技能\n{skill_segment}")
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        for msg in context_messages:
            if msg.role in ("user", "assistant", "system"):
                messages.append({"role": msg.role, "content": msg.content})
            elif msg.role == "function_call":
                messages.append({"role": "assistant", "content": msg.content})
            elif msg.role == "function_result":
                messages.append({"role": "user", "content": f"[技能执行结果] {msg.content}"})
        return messages

    def _send_normal(self, db: Session, session: ChatSession, llm_messages: list, api_base: str, api_key: str) -> dict:
        settings = get_settings()
        try:
            response_content, usage = _call_llm(
                llm_messages,
                model_name=session.model_name,
                max_tokens=settings.llm_max_tokens,
            )
            if isinstance(response_content, dict):
                response_content = json.dumps(response_content, ensure_ascii=False, indent=2)
            reasoning_content = usage.get("reasoning_content", "") or ""
            context_usage = context_manager.calculate_usage(db, session.id, session.context_max_tokens)
            assistant_msg = ChatMessage(
                session_id=session.id,
                role="assistant",
                content=response_content,
                reasoning_content=reasoning_content if reasoning_content else None,
                token_count=usage.get("completion_tokens", 0),
                model_used=session.model_name or settings.llm_model,
                context_usage_pct=context_usage["usage_pct"],
            )
            db.add(assistant_msg)
            session.message_count += 1
            session.total_tokens += usage.get("total_tokens", 0)
            session.updated_at = datetime.utcnow()
            db.commit()
            return {
                "message_id": assistant_msg.id,
                "content": response_content,
                "reasoning_content": reasoning_content,
                "usage": usage,
                "context_usage": context_usage,
            }
        except Exception as e:
            return {"error": str(e)}

    def _send_stream(self, db: Session, session: ChatSession, llm_messages: list, api_base: str, api_key: str):
        settings = get_settings()
        collected = []
        usage_info = None
        for chunk in _call_llm_stream(
            llm_messages,
            model_name=session.model_name,
            api_base=api_base,
            api_key=api_key,
            max_tokens=settings.llm_max_tokens,
        ):
            if isinstance(chunk, tuple) and chunk[0] == "__usage__":
                usage_info = chunk[1]
            else:
                collected.append(chunk)
                yield chunk
        full_content = "".join(collected)
        reasoning_content = usage_info.get("reasoning_content", "") if usage_info else ""
        context_usage = context_manager.calculate_usage(db, session.id, session.context_max_tokens)
        assistant_msg = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=full_content,
            reasoning_content=reasoning_content if reasoning_content else None,
            token_count=usage_info.get("completion_tokens", 0) if usage_info else len(full_content) // 4,
            model_used=session.model_name or settings.llm_model,
            context_usage_pct=context_usage["usage_pct"],
        )
        db.add(assistant_msg)
        session.message_count += 1
        if usage_info:
            session.total_tokens += usage_info.get("total_tokens", 0)
        session.updated_at = datetime.utcnow()
        db.commit()

    def _send_with_tools(self, db: Session, session: ChatSession, llm_messages: list, tools: list, api_base: str, api_key: str, stream: bool = False) -> dict:
        settings = get_settings()
        try:
            result, usage = _call_llm_with_tools(
                llm_messages, tools,
                model_name=session.model_name,
                api_base=api_base,
                api_key=api_key,
                max_tokens=settings.llm_max_tokens,
            )
            tool_calls = result.get("tool_calls", [])
            if tool_calls:
                for tc in tool_calls:
                    func_name = tc["function"]["name"]
                    func_args = tc["function"]["arguments"]
                    call_msg = ChatMessage(
                        session_id=session.id,
                        role="function_call",
                        content=f"调用技能: {func_name}({func_args})",
                        skill_calls=json.dumps([{"name": func_name, "arguments": func_args}], ensure_ascii=False),
                        token_count=0,
                        model_used=session.model_name or settings.llm_model,
                    )
                    db.add(call_msg)
                    session.message_count += 1
                    resolved = function_caller.resolve_tool_call(db, func_name, func_args)
                    if "error" in resolved:
                        skill_result = resolved["error"]
                    else:
                        skill_result = function_caller.execute_skill_call(db, resolved, "")
                    result_msg = ChatMessage(
                        session_id=session.id,
                        role="function_result",
                        content=skill_result[:2000],
                        skill_calls=json.dumps([{"name": func_name, "result_summary": skill_result[:200]}], ensure_ascii=False),
                        token_count=len(skill_result) // 4,
                        model_used=session.model_name or settings.llm_model,
                    )
                    db.add(result_msg)
                    session.message_count += 1
                db.commit()
                return self._send_normal(db, session, llm_messages, api_base, api_key)
            content = result.get("content", "")
            reasoning_content = result.get("reasoning_content", "") or ""
            context_usage = context_manager.calculate_usage(db, session.id, session.context_max_tokens)
            assistant_msg = ChatMessage(
                session_id=session.id,
                role="assistant",
                content=content,
                reasoning_content=reasoning_content if reasoning_content else None,
                token_count=usage.get("completion_tokens", 0),
                model_used=session.model_name or settings.llm_model,
                context_usage_pct=context_usage["usage_pct"],
            )
            db.add(assistant_msg)
            session.message_count += 1
            session.total_tokens += usage.get("total_tokens", 0)
            session.updated_at = datetime.utcnow()
            db.commit()
            return {
                "message_id": assistant_msg.id,
                "content": content,
                "reasoning_content": reasoning_content,
                "usage": usage,
                "context_usage": context_usage,
                "tool_calls": tool_calls,
            }
        except Exception as e:
            return {"error": str(e)}

    def compress_context(self, db: Session, session_id: int) -> dict:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            return {"error": "会话不存在"}
        before = context_manager.calculate_usage(db, session_id, session.context_max_tokens)
        context_manager.build_context_window(db, session_id, session.context_max_tokens, "summary")
        after = context_manager.calculate_usage(db, session_id, session.context_max_tokens)
        return {"before": before, "after": after}

    def get_context_usage(self, db: Session, session_id: int) -> dict:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            return {"error": "会话不存在"}
        return context_manager.calculate_usage(db, session_id, session.context_max_tokens)


chat_engine = ChatEngine()
