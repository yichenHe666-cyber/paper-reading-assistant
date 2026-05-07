from sqlalchemy.orm import Session
from app.services.llm_utils import _call_llm


class ContextCompressor:

    def compress(self, messages: list, db: Session = None, chunk_size: int = 8) -> str:
        if not messages:
            return ""
        if len(messages) <= 3:
            return " ".join(m.content[:200] for m in messages if m.content)
        chunks = []
        for i in range(0, len(messages), chunk_size):
            chunks.append(messages[i:i + chunk_size])
        summaries = []
        for chunk in chunks:
            chunk_text = self._format_chunk(chunk)
            summary = self._summarize_chunk(chunk_text)
            summaries.append(summary)
        return "\n".join(summaries)

    def _format_chunk(self, messages: list) -> str:
        lines = []
        for m in messages:
            role_label = {"user": "用户", "assistant": "助手", "system": "系统", "function_call": "技能调用", "function_result": "技能结果"}.get(m.role, m.role)
            content = m.content[:500] if m.content else ""
            lines.append(f"[{role_label}]: {content}")
        return "\n".join(lines)

    def _summarize_chunk(self, chunk_text: str) -> str:
        prompt = f"""请将以下对话片段压缩为简洁的摘要，保留关键信息、决策和结论。只输出摘要内容，不要额外说明。

对话片段：
{chunk_text}

摘要："""
        messages = [{"role": "user", "content": prompt}]
        try:
            result, _ = _call_llm(messages, max_tokens=300)
            if isinstance(result, str):
                return result.strip()
            return str(result).strip()
        except Exception:
            return chunk_text[:300]


context_compressor = ContextCompressor()
