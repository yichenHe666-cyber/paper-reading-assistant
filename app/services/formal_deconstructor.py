import json
from app.services.llm_service_base import BaseLLMService
from app.services.llm_prompt_builder import PromptBuilder
from app.services.llm_utils import _call_llm, parse_llm_json_response


MAX_CHUNK_CHARS = 8000

_EMPTY_FORMAL_RESULT = {
    "symbol_table": [], "theorems": [], "derivation_checks": [],
    "boundary_conditions": [], "formal_gaps": [],
}


def _split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            break_point = text.rfind("\n\n", start, end)
            if break_point == -1:
                break_point = text.rfind("\n", start, end)
            if break_point == -1 or break_point < start + max_chars // 2:
                break_point = end
            end = break_point
        chunks.append(text[start:end])
        start = end
    return chunks


class FormalDeconstructorService(BaseLLMService):

    def __init__(self):
        super().__init__("形式化拆解")

    def build_prompt(self, chunk: str) -> str:
        builder = PromptBuilder(
            role="理论计算机科学方向的研究员",
            task_description="专精于数学证明的形式化分析与算法复杂度推导",
        )
        builder.add_context("论文片段", chunk[:MAX_CHUNK_CHARS])
        builder.set_output_format({
            "symbol_table": [
                {"symbol": "符号（如 X, θ, P(·)）", "meaning": "原文中的定义", "location": "首次出现位置（如 §3.1 段落2）", "type": "scalar/vector/matrix/set/function/distribution/operator"}
            ],
            "theorems": [
                {"statement": "定理/引理/命题的声明摘要", "proof_summary": "证明概要（20-40字）", "proof_strategy": "类型：induction/contradiction/construction/reduction/probabilistic/compression/diagonalization/direct/other", "location": "定理在文中的位置"}
            ],
            "derivation_checks": [
                {"gap_description": "推导跳步描述", "location": "跳步位置", "my_derivation": ""}
            ],
            "boundary_conditions": [
                {"assumption": "假设（显式或隐式）", "type": "explicit/implicit", "violation_consequence": "违反此假设的预期后果"}
            ],
            "formal_gaps": [
                {"concept": "被提及但未定义的概念/符号", "mention_location": "提及位置", "missing": "缺失的内容描述"}
            ],
        })
        builder.add_academic_constraints_strict()
        builder.add_constraint("derivation_checks.my_derivation 必须留空字符串，供学生填写")
        builder.add_constraint("formal_gaps 要求严格：只要某概念使用了但未给出形式化定义就标记")
        return builder.build()


def _extract_formal_from_chunk(chunk: str) -> dict:
    service = FormalDeconstructorService()
    prompt = service.build_prompt(chunk=chunk)
    messages = [{"role": "user", "content": prompt}]
    content, usage = _call_llm(messages, max_tokens=4096)

    try:
        result = parse_llm_json_response(content, "形式化拆解")
        return result, usage
    except (json.JSONDecodeError, ValueError):
        return dict(_EMPTY_FORMAL_RESULT), usage


def deconstruct_formal_content(paper_text: str) -> dict:
    if not paper_text or len(paper_text.strip()) < 50:
        return {
            **_EMPTY_FORMAL_RESULT,
            "note": "论文文本过短，无法进行形式化拆解",
        }, None

    chunks = _split_text(paper_text)
    if len(chunks) == 1:
        result, usage = _extract_formal_from_chunk(chunks[0])
        return result, usage

    total_usage = None
    merged = dict(_EMPTY_FORMAL_RESULT)

    for i, chunk in enumerate(chunks):
        partial, usage = _extract_formal_from_chunk(chunk)
        if total_usage is None:
            total_usage = usage
        elif usage:
            total_usage["prompt_tokens"] = total_usage.get("prompt_tokens", 0) + usage.get("prompt_tokens", 0)
            total_usage["completion_tokens"] = total_usage.get("completion_tokens", 0) + usage.get("completion_tokens", 0)
            total_usage["total_tokens"] = total_usage.get("total_tokens", 0) + usage.get("total_tokens", 0)

        for key in merged:
            merged[key].extend(partial.get(key, []))

    return merged, total_usage
