import logging
import re

logger = logging.getLogger(__name__)

ACADEMIC_PRIORITY_DOMAINS = [
    "scholar.google.com",
    "webofscience.com",
    "scopus.com",
    "semanticscholar.org",
    "base-search.net",
    "arxiv.org",
    "nature.com",
    "science.org",
    "springer.com",
    "ieeexplore.ieee.org",
    "dl.acm.org",
    "openreview.net",
    "proceedings.neurips.cc",
    "proceedings.mlr.press",
    "aaai.org",
    "ijcai.org",
    "mathscinet.ams.org",
    "zbmath.org",
    "projecteuclid.org",
]

ROUTING_RULES = {
    "fact_check": {
        "domains": ["gov.cn", "people.com.cn", "xinhuanet.com", "cctv.com", "thepaper.cn"],
        "retriever": "duckduckgo",
    },
    "tech": {
        "domains": ["zhihu.com", "csdn.net", "juejin.cn", "segmentfault.com", "stackoverflow.com", "github.com"],
        "retriever": "duckduckgo",
    },
    "academic": {
        "domains": ACADEMIC_PRIORITY_DOMAINS,
        "retriever": "semantic_scholar",
    },
    "general": {
        "domains": [],
        "retriever": "duckduckgo",
    },
}

_FACT_CHECK_PATTERNS = [
    r"是否(真的|确实|属实)",
    r"(真的|确实)是",
    r"(证实|辟谣|真相|事实)",
    r"(数据|统计|比例|人数|金额).*(多少|几|是否)",
]

_TECH_PATTERNS = [
    r"(如何|怎么).*(实现|安装|配置|部署|解决|修复|调试)",
    r"(报错|错误|bug|error|exception|stacktrace)",
    r"(python|java|javascript|typescript|rust|go|c\+\+|docker|k8s|kubernetes)",
    r"(npm|pip|cargo|gradle|maven|yarn)",
]

_ACADEMIC_STRONG_PATTERNS = [
    r'10\.\d{4,}/',
    r'arXiv[:\s]?\d{4}\.\d{4,5}',
    r'\bdoi\b',
    r'\bpaper\b',
    r'论文',
    r'文献',
    r'\bcitation\b',
    r'\babstract\b',
    r'摘要',
    r'\bproceedings\b',
    r'\bjournal\b',
    r'期刊',
    r'\bSOTA\b',
    r'state.of.the.art',
    r'review',
    r'综述',
    r'survey',
    r'影响因子',
    r'\bJCR\b',
    r'h因子',
    r'h指数',
    r'理论',
    r'\btheorem\b',
    r'\bproof\b',
    r'\bconvergence\b',
    r'\boptimization\b',
    r'\balgorithm\b',
    r'\bmodel\b',
    r'\bframework\b',
    r'\bconjecture\b',
    r'\blemma\b',
    r'\baxiom\b',
]

_ACADEMIC_WEAK_PATTERNS = [
    r'引用',
    r'\bbaseline\b',
    r'\bresearch\b',
    r'研究',
    r'\bstudy\b',
    r'\binvestigation\b',
    r'方法',
    r'\bmethod\b',
    r'\bapproach\b',
]


def _detect_search_purpose(query: str) -> str:
    for pattern in _FACT_CHECK_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return "fact_check"

    strong_matches = sum(1 for p in _ACADEMIC_STRONG_PATTERNS if re.search(p, query, re.IGNORECASE))
    weak_matches = sum(1 for p in _ACADEMIC_WEAK_PATTERNS if re.search(p, query, re.IGNORECASE))

    if strong_matches >= 1 or weak_matches >= 2:
        return "academic"

    for pattern in _TECH_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return "tech"

    return "general"


def route_search(query: str) -> dict:
    purpose = _detect_search_purpose(query)
    rule = ROUTING_RULES.get(purpose, ROUTING_RULES["general"])

    return {
        "purpose": purpose,
        "recommended_domains": rule["domains"],
        "recommended_retriever": rule["retriever"],
    }
