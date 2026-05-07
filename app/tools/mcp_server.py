#!/usr/bin/env python3
"""
MCP Server for 核动力科研牛马
供 Claude Code / WorkBuddy 通过 stdio 调用

启动方式:
  docker exec -i reading-assistant python -m app.tools.mcp_server
  # 或本地:
  python -m app.tools.mcp_server
"""
import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

TOOLS = [
    {
        "name": "list_topics",
        "description": "列出所有论文分类主题",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_papers",
        "description": "搜索经典论文",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "topic": {"type": "string", "description": "限定主题（可选）"},
                "limit": {"type": "integer", "description": "返回数量上限", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_paper_detail",
        "description": "获取论文详细信息",
        "inputSchema": {
            "type": "object",
            "properties": {"paper_id": {"type": "string"}},
            "required": ["paper_id"],
        },
    },
    {
        "name": "generate_navigator",
        "description": "生成论文阅读导航（背景知识+核心概念+阅读建议）",
        "inputSchema": {
            "type": "object",
            "properties": {"paper_id": {"type": "string"}},
            "required": ["paper_id"],
        },
    },
    {
        "name": "generate_note_draft",
        "description": "生成论文笔记草稿（Markdown格式）",
        "inputSchema": {
            "type": "object",
            "properties": {"paper_id": {"type": "string"}},
            "required": ["paper_id"],
        },
    },
    {
        "name": "generate_concept_cards",
        "description": "生成概念卡片",
        "inputSchema": {
            "type": "object",
            "properties": {"paper_id": {"type": "string"}},
            "required": ["paper_id"],
        },
    },
    {
        "name": "generate_vocabulary",
        "description": "生成专业词汇表（去重后）",
        "inputSchema": {
            "type": "object",
            "properties": {"paper_id": {"type": "string"}},
            "required": ["paper_id"],
        },
    },
    {
        "name": "write_to_obsidian",
        "description": "一键写入 Obsidian Vault（论文笔记+概念卡片+词汇表）",
        "inputSchema": {
            "type": "object",
            "properties": {"paper_id": {"type": "string"}},
            "required": ["paper_id"],
        },
    },
    {
        "name": "scan_obsidian_vault",
        "description": "扫描 Obsidian Vault，同步阅读状态",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_reading_stats",
        "description": "获取阅读统计",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_llm_cost_today",
        "description": "查询当日 LLM 花费",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def handle_request(request: dict) -> dict:
    method = request.get("method", "")

    if method == "tools/list":
        return {"tools": TOOLS}

    if method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            result = _call_tool(tool_name, arguments)
            return {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
            }
        except Exception as e:
            return {
                "content": [{"type": "text", "text": f"错误: {str(e)}"}],
                "isError": True,
            }

    return {"error": f"Unknown method: {method}"}


def _call_tool(tool_name: str, args: dict):
    from app.database.session import SessionLocal
    db = SessionLocal()
    try:
        if tool_name == "list_topics":
            topics = __import__("app.services.github_fetcher", fromlist=["get_topics"]).get_topics()
            return topics

        elif tool_name == "search_papers":
            import httpx
            q = args.get("query", "")
            limit = args.get("limit", 10)
            topic = args.get("topic")
            params = {"q": q, "limit": limit}
            resp = httpx.get("http://127.0.0.1:8000/api/papers/search", params=params, timeout=30)
            data = resp.json()
            results = data.get("results", [])
            if topic:
                results = [r for r in results if r.get("topic_id") == topic]
            return results[:limit]

        elif tool_name == "get_paper_detail":
            import httpx
            resp = httpx.get(f"http://127.0.0.1:8000/api/papers/{args['paper_id']}", timeout=30)
            return resp.json()

        elif tool_name == "generate_navigator":
            import httpx
            resp = httpx.post("http://127.0.0.1:8000/api/reading/navigator",
                             json={"paper_id": args["paper_id"]}, timeout=120)
            return resp.json()

        elif tool_name == "generate_note_draft":
            import httpx
            paper = httpx.get(f"http://127.0.0.1:8000/api/papers/{args['paper_id']}", timeout=30).json()
            nav = httpx.post("http://127.0.0.1:8000/api/reading/navigator",
                           json={"paper_id": args["paper_id"]}, timeout=120).json()
            resp = httpx.post("http://127.0.0.1:8000/api/reading/note-draft",
                            json={"paper_id": args["paper_id"], "navigator": nav.get("navigator", {})}, timeout=120)
            return resp.json()

        elif tool_name == "generate_concept_cards":
            import httpx
            nav = httpx.post("http://127.0.0.1:8000/api/reading/navigator",
                           json={"paper_id": args["paper_id"]}, timeout=120).json()
            resp = httpx.post("http://127.0.0.1:8000/api/reading/concept-cards",
                            json={"paper_id": args["paper_id"], "navigator": nav.get("navigator", {})}, timeout=120)
            return resp.json()

        elif tool_name == "generate_vocabulary":
            import httpx
            resp = httpx.post("http://127.0.0.1:8000/api/reading/vocabulary",
                            json={"paper_id": args["paper_id"]}, timeout=120)
            return resp.json()

        elif tool_name == "write_to_obsidian":
            import httpx
            oneclick = httpx.post("http://127.0.0.1:8000/api/reading/one-click",
                                json={"paper_id": args["paper_id"]}, timeout=180).json()
            if oneclick.get("error"):
                return oneclick
            resp = httpx.post("http://127.0.0.1:8000/api/obsidian/write-all", json={
                "paper_id": args["paper_id"],
                "note_draft": oneclick.get("note_draft", ""),
                "concept_cards": oneclick.get("concept_cards", []),
                "vocabulary_md": oneclick.get("vocabulary_md", ""),
            }, timeout=30)
            return resp.json()

        elif tool_name == "scan_obsidian_vault":
            import httpx
            resp = httpx.post("http://127.0.0.1:8000/api/obsidian/scan-vault", timeout=30)
            return resp.json()

        elif tool_name == "get_reading_stats":
            import httpx
            resp = httpx.get("http://127.0.0.1:8000/api/system/stats", timeout=30)
            return resp.json()

        elif tool_name == "get_llm_cost_today":
            import httpx
            resp = httpx.get("http://127.0.0.1:8000/api/system/llm-cost", timeout=30)
            return resp.json()

        else:
            return {"error": f"Unknown tool: {tool_name}"}
    finally:
        db.close()


def main():
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
        except json.JSONDecodeError:
            continue

        response = handle_request(request)
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
