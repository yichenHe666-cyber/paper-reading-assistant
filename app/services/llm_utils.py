# -*- coding: utf-8 -*-
import json
import re
import time
from openai import OpenAI
from app.config import get_settings


def _get_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        base_url=settings.llm_api_base,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout,
    )


def _call_llm(messages: list[dict], max_tokens: int = None) -> tuple:
    settings = get_settings()
    client = _get_client()
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                max_tokens=max_tokens or settings.llm_max_tokens,
                temperature=settings.llm_temperature,
            )
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason

            if not content or not content.strip():
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                raise ValueError("LLM returned empty content")

            return content, {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.prompt_tokens + response.usage.completion_tokens,
                "model": settings.llm_model,
                "finish_reason": finish_reason,
            }
        except Exception as e:
            if attempt < max_retries:
                time.sleep(3)
            else:
                raise


def _is_likely_truncated(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    open_braces = text.count("{")
    close_braces = text.count("}")
    open_brackets = text.count("[")
    close_brackets = text.count("]")
    if open_braces != close_braces or open_brackets != close_brackets:
        return True
    if text.endswith('"') or text.endswith(":") or text.endswith(",") or text.endswith("\\"):
        return True
    try:
        json.loads(text)
        return False
    except json.JSONDecodeError:
        return True


def _extract_json(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValueError("LLM returned empty content")

    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    code_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if code_block_match:
        candidate = code_block_match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    first_bracket = text.find("[")
    last_bracket = text.find("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        candidate = text[first_bracket:last_bracket + 1]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot extract valid JSON from LLM output. First 200 chars: {text[:200]}")


def _repair_truncated_json(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return raw

    repaired = raw

    if repaired.endswith(","):
        repaired = repaired[:-1]
    elif repaired.endswith(":"):
        repaired = repaired + '""'

    if repaired.endswith("\\"):
        repaired = repaired[:-1]

    stack = []
    in_string = False
    escape_next = False
    for ch in repaired:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()

    if repaired.endswith('"') and not repaired.endswith('\\"') and not in_string:
        pass
    elif repaired.endswith('"') and in_string:
        repaired += '"'

    closing = "".join(reversed(stack))
    repaired += closing

    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        pass

    first_brace = repaired.find("{")
    last_brace = repaired.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = repaired[first_brace:last_brace + 1]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return raw


def _fix_truncated_json_with_llm(raw: str, paper_title: str = "") -> dict:
    settings = get_settings()
    client = _get_client()
    fix_prompt = f"""Below is an incomplete JSON string. Complete it to make it valid JSON. Output only the completed JSON, no explanation.

Incomplete content:
{raw}

Output valid JSON only:"""
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": fix_prompt}],
        max_tokens=settings.llm_max_tokens,
        temperature=0.1,
    )
    fixed = response.choices[0].message.content
    return json.loads(_extract_json(fixed))


def parse_llm_json_response(content: str, context_hint: str = "") -> dict:
    if not content or not content.strip():
        raise ValueError("LLM返回空内容")

    try:
        json_str = _extract_json(content)
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        pass

    if _is_likely_truncated(content):
        repaired = _repair_truncated_json(content)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        try:
            return _fix_truncated_json_with_llm(content, context_hint)
        except Exception as e:
            raise ValueError(
                f"LLM返回的JSON被截断且自动修复失败: {e}\n"
                f"上下文: {context_hint}\n"
                f"原始内容前300字: {content[:300]}"
            )

    raise ValueError(
        f"无法解析LLM返回的JSON内容\n"
        f"上下文: {context_hint}\n"
        f"原始内容前300字: {content[:300]}"
    )
