import asyncio
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

GPTR_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "gpt-researcher")
)


def _ensure_gptr_on_path():
    if GPTR_PATH not in sys.path:
        sys.path.insert(0, GPTR_PATH)


def _configure_gptr_env():
    from app.config import get_settings

    settings = get_settings()

    if settings.llm_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.llm_api_key)
    if settings.llm_api_base:
        os.environ.setdefault("OPENAI_BASE_URL", settings.llm_api_base)

    os.environ.setdefault("RETRIEVER", "duckduckgo")
    os.environ.setdefault("FAST_LLM", f"openai:{settings.llm_model}")
    os.environ.setdefault("SMART_LLM", f"openai:{settings.llm_model}")
    os.environ.setdefault("LANGUAGE", "chinese")


async def conduct_research(
    query: str,
    report_type: str = "research_report",
    report_source: str = "web",
    tone: str = "Objective",
    query_domains: list[str] = None,
) -> dict:
    _ensure_gptr_on_path()
    _configure_gptr_env()

    try:
        from gpt_researcher import GPTResearcher
    except ImportError as e:
        logger.error(f"Failed to import GPTResearcher: {e}")
        return {"error": f"GPTResearcher import failed: {e}"}

    try:
        researcher = GPTResearcher(
            query=query,
            report_type=report_type,
            report_source=report_source,
            tone=tone,
            query_domains=query_domains,
        )

        await researcher.conduct_research()
        report = await researcher.write_report()

        source_urls = researcher.get_source_urls()
        costs = researcher.get_costs()

        return {
            "report": report,
            "source_urls": source_urls if isinstance(source_urls, list) else list(source_urls) if source_urls else [],
            "costs": costs,
            "visited_urls": list(researcher.visited_urls) if hasattr(researcher, "visited_urls") else [],
        }
    except Exception as e:
        logger.error(f"Research failed: {e}", exc_info=True)
        return {"error": str(e)}


def run_research_sync(
    query: str,
    report_type: str = "research_report",
    report_source: str = "web",
    tone: str = "Objective",
    query_domains: list[str] = None,
) -> dict:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    conduct_research(query, report_type, report_source, tone, query_domains),
                )
                return future.result(timeout=600)
        else:
            return loop.run_until_complete(
                conduct_research(query, report_type, report_source, tone, query_domains)
            )
    except RuntimeError:
        return asyncio.run(
            conduct_research(query, report_type, report_source, tone, query_domains)
        )
