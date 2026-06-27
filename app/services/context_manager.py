from sqlalchemy.orm import Session
from app.models.chat_message import ChatMessage
from app.config import get_settings


class ContextManager:

    def calculate_usage(self, db: Session, session_id: int, context_max_tokens: int) -> dict:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        total_tokens = sum(m.token_count or 0 for m in messages)
        usage_pct = (total_tokens / context_max_tokens * 100) if context_max_tokens > 0 else 0
        level = "normal"
        settings = get_settings()
        if usage_pct > settings.context_compress_threshold * 100:
            level = "high"
        if usage_pct > 95:
            level = "danger"
        return {
            "total_tokens": total_tokens,
            "max_tokens": context_max_tokens,
            "usage_pct": round(usage_pct, 1),
            "level": level,
            "message_count": len(messages),
        }

    def build_context_window(self, db: Session, session_id: int, context_max_tokens: int, strategy: str = "sliding_window") -> list:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        if not messages:
            return []
        if strategy == "sliding_window":
            return self._sliding_window(messages, context_max_tokens)
        elif strategy == "summary":
            return self._summary_strategy(messages, context_max_tokens, db, session_id)
        elif strategy == "hybrid":
            return self._hybrid_strategy(messages, context_max_tokens, db, session_id)
        return self._sliding_window(messages, context_max_tokens)

    def _sliding_window(self, messages: list, context_max_tokens: int) -> list:
        target = int(context_max_tokens * 0.9)
        total = 0
        result = []
        for msg in reversed(messages):
            msg_tokens = msg.token_count or 0
            if total + msg_tokens > target and result:
                break
            result.insert(0, msg)
            total += msg_tokens
        return result

    def _summary_strategy(self, messages: list, context_max_tokens: int, db: Session, session_id: int) -> list:
        if len(messages) <= 5:
            return messages
        from app.services.context_compressor import context_compressor
        old_messages = messages[:-5]
        recent_messages = messages[-5:]
        summary_text = context_compressor.compress(old_messages, db)
        summary_msg = ChatMessage(
            session_id=session_id,
            role="system",
            content=f"[历史对话摘要] {summary_text}",
            token_count=len(summary_text) // 4,
        )
        # Persist the summary and remove the compressed old messages so that
        # calculate_usage() reflects the reduced token count (before > after).
        db.add(summary_msg)
        for m in old_messages:
            db.delete(m)
        db.commit()
        return [summary_msg] + recent_messages

    def _hybrid_strategy(self, messages: list, context_max_tokens: int, db: Session, session_id: int) -> list:
        if len(messages) <= 5:
            return messages
        from app.services.context_compressor import context_compressor
        old_messages = messages[:-5]
        recent_messages = messages[-5:]
        key_messages = [m for m in old_messages if m.role in ("function_call", "function_result")]
        non_key = [m for m in old_messages if m.role not in ("function_call", "function_result")]
        summary_text = context_compressor.compress(non_key, db) if non_key else ""
        result = []
        if summary_text:
            summary_msg = ChatMessage(
                session_id=session_id,
                role="system",
                content=f"[历史对话摘要] {summary_text}",
                token_count=len(summary_text) // 4,
            )
            result.append(summary_msg)
        result.extend(key_messages)
        result.extend(recent_messages)
        return result

    def should_compress(self, db: Session, session_id: int, context_max_tokens: int) -> bool:
        usage = self.calculate_usage(db, session_id, context_max_tokens)
        settings = get_settings()
        return usage["usage_pct"] > settings.context_compress_threshold * 100


context_manager = ContextManager()
