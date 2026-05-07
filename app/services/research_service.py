import asyncio
import json
import logging
import os
import time
import threading

logger = logging.getLogger(__name__)


def _configure_gptr_env():
    from app.config import get_settings

    settings = get_settings()

    if settings.llm_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.llm_api_key)
    if settings.llm_api_base:
        os.environ.setdefault("OPENAI_BASE_URL", settings.llm_api_base)

    os.environ.setdefault("RETRIEVER", settings.retriever)
    os.environ.setdefault("FAST_LLM", f"openai:{settings.llm_model}")
    os.environ.setdefault("SMART_LLM", f"openai:{settings.llm_model}")
    os.environ.setdefault("LANGUAGE", "chinese")

    if settings.tavily_api_key:
        os.environ.setdefault("TAVILY_API_KEY", settings.tavily_api_key)
    if settings.google_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
    if settings.google_cx:
        os.environ.setdefault("GOOGLE_CX_KEY", settings.google_cx)
    if settings.bing_api_key:
        os.environ.setdefault("BING_API_KEY", settings.bing_api_key)
    if settings.serper_api_key:
        os.environ.setdefault("SERPER_API_KEY", settings.serper_api_key)
    if settings.exa_api_key:
        os.environ.setdefault("EXA_API_KEY", settings.exa_api_key)

    os.environ.setdefault("REASONING_EFFORT", settings.llm_reasoning_effort)


_search_rate_limiter_lock = threading.Lock()
_search_rate_limiter_last_call = 0.0


def _enforce_rate_limit():
    global _search_rate_limiter_last_call
    from app.config import get_settings
    settings = get_settings()
    min_interval = settings.search_rate_limit_interval
    with _search_rate_limiter_lock:
        elapsed = time.time() - _search_rate_limiter_last_call
        if elapsed < min_interval:
            wait = min_interval - elapsed
            time.sleep(wait)
        _search_rate_limiter_last_call = time.time()


def _is_academic_query(query: str) -> bool:
    import re
    academic_patterns = [
        r'10\.\d{4,}/',
        r'arXiv[:\s]?\d{4}\.\d{4,5}',
        r'\bdoi[:\s]?',
        r'\bpaper\b.*\btitle\b',
        r'\babstract\b',
        r'\bproceedings\b',
        r'\bjournal\b',
        r'\bcitation\b',
        r'\bbibliography\b',
    ]
    return any(re.search(p, query, re.IGNORECASE) for p in academic_patterns)


def _get_fallback_chain() -> list[str]:
    from app.config import get_settings
    settings = get_settings()
    chain_str = settings.search_fallback_chain
    return [r.strip() for r in chain_str.split(",") if r.strip()]


def _get_retrievers_for_query(query: str) -> list[str]:
    from app.services.search_router import route_search

    chain = _get_fallback_chain()
    routing = route_search(query)

    if routing["purpose"] == "academic":
        academic_priority = ["semantic_scholar", "arxiv"]
        for engine in reversed(academic_priority):
            if engine in chain:
                chain.remove(engine)
            chain.insert(0, engine)
    elif _is_academic_query(query):
        academic = ["arxiv", "semantic_scholar"]
        for engine in academic:
            if engine not in chain:
                chain.insert(0, engine)
            elif chain.index(engine) > 0:
                chain.remove(engine)
                chain.insert(0, engine)

    return chain


def _check_retriever_available(retriever_name: str) -> bool:
    from app.config import get_settings
    settings = get_settings()
    key_map = {
        "tavily": settings.tavily_api_key,
        "google": settings.google_api_key,
        "bing": settings.bing_api_key,
        "serper": settings.serper_api_key,
        "exa": settings.exa_api_key,
    }
    if retriever_name in key_map:
        return bool(key_map[retriever_name])
    return True


async def _conduct_research_with_retriever(
    query: str,
    retriever: str,
    report_type: str = "research_report",
    report_source: str = "web",
    tone: str = "Objective",
    query_domains: list[str] = None,
) -> dict:
    from gpt_researcher import GPTResearcher
    from urllib.parse import urlparse

    os.environ["RETRIEVER"] = retriever

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

    source_list = source_urls if isinstance(source_urls, list) else list(source_urls) if source_urls else []
    visited_list = list(researcher.visited_urls) if hasattr(researcher, "visited_urls") else []

    if query_domains:
        def _domain_matches(url: str) -> bool:
            try:
                hostname = urlparse(url).hostname or ""
                return any(hostname == d or hostname.endswith("." + d) for d in query_domains)
            except Exception:
                return False

        source_list = [u for u in source_list if _domain_matches(u)]
        visited_list = [u for u in visited_list if _domain_matches(u)]

    return {
        "report": report,
        "source_urls": source_list,
        "costs": costs,
        "visited_urls": visited_list,
        "retriever_used": retriever,
    }


async def conduct_research(
    query: str,
    report_type: str = "research_report",
    report_source: str = "web",
    tone: str = "Objective",
    query_domains: list[str] = None,
) -> dict:
    from app.config import get_settings
    from app.services.search_quality import evaluate_search_quality
    from app.services.search_router import route_search

    settings = get_settings()
    _configure_gptr_env()

    try:
        from gpt_researcher import GPTResearcher
    except ImportError as e:
        logger.error(f"Failed to import GPTResearcher: {e}")
        return {"error": f"GPTResearcher import failed: {e}"}

    routing = route_search(query)
    if not query_domains and routing["recommended_domains"]:
        query_domains = routing["recommended_domains"]

    retrievers = _get_retrievers_for_query(query)
    if routing["recommended_retriever"] not in retrievers:
        retrievers.insert(0, routing["recommended_retriever"])

    fallback_log = []
    max_retries = settings.search_max_retries
    base_delay = settings.search_retry_base_delay

    for retriever_name in retrievers:
        if not _check_retriever_available(retriever_name):
            fallback_log.append({
                "retriever": retriever_name,
                "status": "skipped",
                "reason": "API Key 未配置",
            })
            continue

        for attempt in range(max_retries):
            try:
                _enforce_rate_limit()
                result = await _conduct_research_with_retriever(
                    query=query,
                    retriever=retriever_name,
                    report_type=report_type,
                    report_source=report_source,
                    tone=tone,
                    query_domains=query_domains,
                )

                if result.get("source_urls") or result.get("report"):
                    result["fallback_log"] = fallback_log

                    quality = evaluate_search_quality(
                        source_urls=result.get("source_urls", []),
                        query=query,
                        visited_urls=result.get("visited_urls", []),
                    )
                    result["quality_metrics"] = quality
                    result["search_purpose"] = routing["purpose"]

                    return result

                fallback_log.append({
                    "retriever": retriever_name,
                    "status": "empty",
                    "attempt": attempt + 1,
                    "reason": "搜索返回空结果",
                })

            except Exception as e:
                err_str = str(e)
                fallback_log.append({
                    "retriever": retriever_name,
                    "status": "error",
                    "attempt": attempt + 1,
                    "reason": err_str[:200],
                })

                if "429" in err_str or "rate" in err_str.lower():
                    wait = base_delay * (4 ** attempt)
                    logger.warning(f"搜索限流 {retriever_name} (尝试 {attempt+1}/{max_retries})，{wait}s 后重试")
                    await asyncio.sleep(wait)
                    continue

                if "timeout" in err_str.lower() or "connection" in err_str.lower():
                    wait = base_delay * (2 ** attempt)
                    logger.warning(f"搜索超时 {retriever_name} (尝试 {attempt+1}/{max_retries})，{wait}s 后重试")
                    await asyncio.sleep(wait)
                    continue

                break

        fallback_log.append({
            "retriever": retriever_name,
            "status": "exhausted",
            "reason": f"重试 {max_retries} 次后仍失败",
        })

    return {
        "error": "所有搜索引擎均失败",
        "fallback_log": fallback_log,
    }


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
