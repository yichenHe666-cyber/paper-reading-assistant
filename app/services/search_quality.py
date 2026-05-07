import logging
import re
from urllib.parse import urlparse
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

HIGH_QUALITY_DOMAINS = {
    "gov.cn", "gov.hk", "gov.tw",
    "edu.cn", "ac.cn", "ac.uk", "edu", "ac.jp",
    "xinhuanet.com", "people.com.cn", "cctv.com",
    "thepaper.cn", "caixin.com", "ftchinese.com",
    "nature.com", "science.org", "springer.com",
    "ieeexplore.ieee.org", "dl.acm.org",
    "arxiv.org", "semanticscholar.org",
    "scholar.google.com", "researchgate.net",
    "webofscience.com", "webofscience.clarivate.cn",
    "scopus.com", "elsevier.com",
    "base-search.net",
    "openreview.net",
    "proceedings.neurips.cc",
    "proceedings.mlr.press",
    "aaai.org",
    "ijcai.org",
    "mathscinet.ams.org",
    "zbmath.org",
    "projecteuclid.org",
}


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.hostname or ""
    except Exception:
        return ""


def _is_high_quality(domain: str) -> bool:
    if not domain:
        return False
    for hq in HIGH_QUALITY_DOMAINS:
        if domain == hq or domain.endswith("." + hq):
            return True
    return False


def _estimate_freshness_days(url: str) -> float:
    return 30.0


def evaluate_search_quality(
    source_urls: list[str],
    query: str,
    visited_urls: list[str] = None,
) -> dict:
    source_count = len(source_urls)

    high_quality_count = 0
    for url in source_urls:
        domain = _extract_domain(url)
        if _is_high_quality(domain):
            high_quality_count += 1

    high_quality_ratio = high_quality_count / source_count if source_count > 0 else 0.0

    total_freshness = 0.0
    for url in source_urls:
        total_freshness += _estimate_freshness_days(url)
    avg_freshness_days = total_freshness / source_count if source_count > 0 else 999.0

    query_words = set(re.findall(r'\w+', query.lower()))
    matched_words = 0
    for url in source_urls:
        url_lower = url.lower()
        for word in query_words:
            if len(word) > 2 and word in url_lower:
                matched_words += 1
                break
    coverage_score = matched_words / len(query_words) if query_words else 0.0
    coverage_score = min(coverage_score, 1.0)

    is_low_quality = high_quality_ratio < 0.3 or source_count < 3
    warning = ""
    if is_low_quality:
        warning = "⚠️ 搜索结果质量较低，建议更换关键词或搜索引擎"

    return {
        "source_count": source_count,
        "high_quality_ratio": round(high_quality_ratio, 3),
        "avg_freshness_days": round(avg_freshness_days, 1),
        "coverage_score": round(coverage_score, 3),
        "is_low_quality": is_low_quality,
        "warning": warning,
    }
