import httpx
import time
import re
from typing import Optional
from app.models.topic import Topic
from app.config import get_settings

GITHUB_API_BASE = "https://api.github.com"

def _github_headers() -> dict:
    """Build GitHub API headers with optional authentication."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "paper-reading-assistant/1.0",
    }
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

TOPIC_ICONS = {
    "affective_computing": "face-smile-beam",
    "android": "robot",
    "api_design": "plug",
    "artificial_intelligence": "brain",
    "audio_comp_sci": "music",
    "biocomputing": "dna",
    "bioinformatics": "dna",
    "brain-computer-interface": "brain",
    "caching": "memory",
    "combinatory_logic": "shapes",
    "comp_sci_fundamentals_and_history": "landmark",
    "computational_creativity": "palette",
    "computer_architecture": "microchip",
    "computer_education": "graduation-cap",
    "computer_graphics": "image",
    "computer_vision": "eye",
    "concurrency": "bolt",
    "crash_only": "bomb",
    "cryptography": "key",
    "data_compression": "compress",
    "data_fusion": "object-group",
    "data_replication": "copy",
    "data_science": "flask",
    "data_structures": "sitemap",
    "database": "database",
    "datastores": "database",
    "design": "pen-ruler",
    "digital_currency": "coins",
    "distributed-file-systems": "folder-tree",
    "distributed_systems": "network-wired",
    "economics": "chart-line",
    "ethics": "scale-balanced",
    "experimental_algorithmics": "vial",
    "experimental_design": "flask",
    "faults_and_verification": "clipboard-check",
    "functional_programming": "code",
    "gamification": "gamepad",
    "game_theory": "chess",
    "garbage_collection": "trash-can",
    "gossip": "comments",
    "human_computer_interaction": "hand-pointer",
    "information_retrieval": "magnifying-glass",
    "information_theory": "tower-broadcast",
    "languages": "code",
    "languages-paradigms": "cubes",
    "languages-theory": "book",
    "logic_and_programming": "code",
    "machine_learning": "robot",
    "macroeconomics": "chart-line",
    "macros": "gears",
    "mathematics": "calculator",
    "memory_management": "memory",
    "natural_language_processing": "comments",
    "networking": "globe",
    "networks": "network-wired",
    "neuroscience": "brain",
    "non_blocking_algorithms": "bolt",
    "operating_systems": "laptop-code",
    "pattern_matching": "magnifying-glass",
    "pattern_stringology": "shapes",
    "philosophy": "lightbulb",
    "physics": "atom",
    "privacy": "user-shield",
    "processes": "gears",
    "programming_languages": "code",
    "programming_paradigms": "cubes",
    "quantum_computing": "atom",
    "robotics": "robot",
    "scripts": "scroll",
    "search": "magnifying-glass",
    "search-engines": "magnifying-glass-plus",
    "security": "shield-halved",
    "social-science": "users",
    "software_engineering": "gears",
    "software_engineering_orgs": "building",
    "software_testing": "vial",
    "speech_recognition": "microphone",
    "sports_analytics": "futbol",
    "statistics": "chart-column",
    "streaming_algorithms": "water",
    "sublinear_algorithms": "bolt",
    "systematic_review": "book-open",
    "systems_modeling": "diagram-project",
    "temporal_data": "clock",
    "testing": "vial",
    "time_series": "chart-line",
    "type_theory": "tag",
    "unikernels": "box",
    "user_interfaces": "desktop",
    "virtual_machines": "server",
    "virtual_reality": "vr-cardboard",
    "virtualization": "server",
}

TOPIC_NAMES_CN = {
    "affective_computing": "情感计算",
    "android": "Android",
    "api_design": "API设计",
    "artificial_intelligence": "人工智能",
    "audio_comp_sci": "音频计算",
    "biocomputing": "生物计算",
    "bioinformatics": "生物信息学",
    "brain-computer-interface": "脑机接口",
    "caching": "缓存",
    "combinatory_logic": "组合逻辑",
    "comp_sci_fundamentals_and_history": "CS基础与历史",
    "computational_creativity": "计算创意",
    "computer_architecture": "计算机体系结构",
    "computer_education": "计算机教育",
    "computer_graphics": "计算机图形学",
    "computer_vision": "计算机视觉",
    "concurrency": "并发",
    "crash_only": "崩溃即设计",
    "cryptography": "密码学",
    "data_compression": "数据压缩",
    "data_fusion": "数据融合",
    "data_replication": "数据复制",
    "data_science": "数据科学",
    "data_structures": "数据结构",
    "database": "数据库",
    "datastores": "数据存储",
    "design": "设计",
    "digital_currency": "数字货币",
    "distributed-file-systems": "分布式文件系统",
    "distributed_systems": "分布式系统",
    "economics": "经济学",
    "ethics": "伦理",
    "experimental_algorithmics": "实验算法学",
    "experimental_design": "实验设计",
    "faults_and_verification": "容错与验证",
    "functional_programming": "函数式编程",
    "gamification": "游戏化",
    "game_theory": "博弈论",
    "garbage_collection": "垃圾回收",
    "gossip": "Gossip协议",
    "human_computer_interaction": "人机交互",
    "information_retrieval": "信息检索",
    "information_theory": "信息论",
    "languages": "编程语言理论",
    "languages-paradigms": "编程范式",
    "languages-theory": "语言理论",
    "logic_and_programming": "逻辑与编程",
    "machine_learning": "机器学习",
    "macroeconomics": "宏观经济学",
    "macros": "宏",
    "mathematics": "数学",
    "memory_management": "内存管理",
    "natural_language_processing": "自然语言处理",
    "networking": "网络",
    "networks": "网络",
    "neuroscience": "神经科学",
    "non_blocking_algorithms": "非阻塞算法",
    "operating_systems": "操作系统",
    "pattern_matching": "模式匹配",
    "pattern_stringology": "字符串模式",
    "philosophy": "哲学",
    "physics": "物理",
    "privacy": "隐私",
    "processes": "进程",
    "programming_languages": "编程语言",
    "programming_paradigms": "编程范式",
    "quantum_computing": "量子计算",
    "robotics": "机器人学",
    "scripts": "脚本工具",
    "search": "搜索",
    "search-engines": "搜索引擎",
    "security": "安全",
    "social-science": "社会科学",
    "software_engineering": "软件工程",
    "software_engineering_orgs": "软件工程组织",
    "software_testing": "软件测试",
    "speech_recognition": "语音识别",
    "sports_analytics": "体育分析",
    "statistics": "统计学",
    "streaming_algorithms": "流算法",
    "sublinear_algorithms": "次线性算法",
    "systematic_review": "系统综述",
    "systems_modeling": "系统建模",
    "temporal_data": "时序数据",
    "testing": "测试",
    "time_series": "时间序列",
    "type_theory": "类型论",
    "unikernels": "Unikernel",
    "user_interfaces": "用户界面",
    "virtual_machines": "虚拟机",
    "virtual_reality": "虚拟现实",
    "virtualization": "虚拟化",
}


def get_topics(repo: str = "papers-we-love/papers-we-love") -> list[dict]:
    url = f"{GITHUB_API_BASE}/repos/{repo}/contents/"
    resp = httpx.get(url, timeout=30, headers=_github_headers())
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining", "0")
        if remaining == "0":
            reset_time = int(resp.headers.get("X-RateLimit-Reset", "0"))
            wait = max(reset_time - time.time(), 30)
            if wait > 300:
                raise Exception(f"GitHub API 限流，请在 {int(wait/60)} 分钟后重试，或配置 GITHUB_TOKEN（认证用户 5000次/小时）")
            time.sleep(min(wait, 120))
            return get_topics(repo)
        resp.raise_for_status()
    resp.raise_for_status()
    entries = resp.json()
    topics = []
    for entry in entries:
        if entry["type"] == "dir" and not entry["name"].startswith("."):
            topics.append({
                "id": entry["name"],
                "name": entry["name"].replace("_", " ").title(),
                "name_cn": TOPIC_NAMES_CN.get(entry["name"], entry["name"].replace("_", " ").title()),
                "icon": TOPIC_ICONS.get(entry["name"], "📄"),
                "fa_icon": TOPIC_ICONS.get(entry["name"], "file-lines"),
                "path": entry["path"],
            })
    return sorted(topics, key=lambda t: t["name"])


def get_topic_readme(topic_id: str, repo: str = "papers-we-love/papers-we-love") -> Optional[str]:
    url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{topic_id}/README.md"
    resp = httpx.get(url, timeout=15, headers=_github_headers())
    if resp.status_code == 404:
        return None
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining", "0")
        if remaining == "0":
            reset_time = int(resp.headers.get("X-RateLimit-Reset", "0"))
            wait = max(reset_time - time.time(), 30)
            time.sleep(min(wait, 60))
            return get_topic_readme(topic_id, repo)
        resp.raise_for_status()
    resp.raise_for_status()
    data = resp.json()
    import base64
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content


def sync_all_papers(db_session, repo: str = "papers-we-love/papers-we-love", force: bool = False) -> dict:
    new_count = 0
    updated_count = 0
    total = 0
    topics_processed = 0

    topics_list = get_topics(repo)

    for topic_info in topics_list:
        tid = topic_info["id"]
        existing_topic = db_session.query(Topic).filter(Topic.id == tid).first()
        if not existing_topic:
            db_session.add(Topic(
                id=tid,
                name=topic_info["name"],
                name_cn=topic_info["name_cn"],
                icon=topic_info["icon"],
                fa_icon=topic_info.get("fa_icon", "file-lines"),
                paper_count=0,
            ))
        else:
            existing_topic.name = topic_info["name"]
            existing_topic.name_cn = topic_info["name_cn"]
            existing_topic.icon = topic_info["icon"]
            existing_topic.fa_icon = topic_info.get("fa_icon", "file-lines")

        db_session.commit()

        from app.models.paper import Paper
        existing_paper_count = db_session.query(Paper).filter(Paper.topic_id == tid).count()

        if not force and existing_paper_count > 0:
            existing_topic = db_session.query(Topic).filter(Topic.id == tid).first()
            if existing_topic:
                existing_topic.paper_count = existing_paper_count
            db_session.commit()
            continue

        md_content = None
        try:
            md_content = get_topic_readme(tid, repo)
        except Exception:
            pass

        if not md_content:
            existing_topic = db_session.query(Topic).filter(Topic.id == tid).first()
            if existing_topic:
                existing_topic.paper_count = existing_paper_count
            db_session.commit()
            continue

        topics_processed += 1
        from app.services.paper_parser import parse_readme_to_papers
        papers = parse_readme_to_papers(md_content, tid)

        from app.models.paper import Paper
        topic_count = 0
        for p in papers:
            existing = db_session.query(Paper).filter(Paper.id == p["id"]).first()
            if not existing:
                existing = db_session.query(Paper).filter(
                    Paper.title == p["title"],
                    Paper.authors == p["authors"]
                ).first()
            if existing:
                changed = False
                if existing.title != p["title"]:
                    existing.title = p["title"]; changed = True
                if existing.authors != p["authors"]:
                    existing.authors = p["authors"]; changed = True
                if existing.year != p.get("year"):
                    existing.year = p.get("year"); changed = True
                if existing.pdf_url != p.get("pdf_url"):
                    existing.pdf_url = p.get("pdf_url"); changed = True
                if changed:
                    updated_count += 1
                topic_count += 1
            else:
                db_session.add(Paper(
                    id=p["id"],
                    title=p["title"],
                    authors=p["authors"],
                    year=p.get("year"),
                    topic_id=tid,
                    subtopic=p.get("subtopic"),
                    pdf_url=p.get("pdf_url"),
                    community_notes_url=p.get("community_notes_url"),
                    abstract=p.get("abstract"),
                ))
                new_count += 1
                topic_count += 1
            total += 1

        existing_topic = db_session.query(Topic).filter(Topic.id == tid).first()
        if existing_topic:
            existing_topic.paper_count = topic_count

        db_session.commit()
        time.sleep(0.1)

    from sqlalchemy import text
    db_session.execute(text("""
        UPDATE topics
        SET paper_count = (SELECT COUNT(*) FROM papers WHERE papers.topic_id = topics.id)
    """))
    db_session.commit()

    from app.models.paper import Paper as PaperModel
    actual_total = db_session.query(PaperModel).count()

    missing_authors = db_session.query(PaperModel).filter(
        (PaperModel.authors.is_(None)) |
        (PaperModel.authors == "") |
        (PaperModel.authors == "[]") |
        (PaperModel.authors == '["Unknown"]')
    ).count()
    missing_year = db_session.query(PaperModel).filter(PaperModel.year.is_(None)).count()

    empty_topics = db_session.query(Topic).filter(
        Topic.id.notin_(db_session.query(Paper.topic_id).distinct())
    ).count()

    quality_issues = []
    if actual_total > 0:
        if missing_authors / actual_total > 0.5:
            quality_issues.append(f"作者缺失率过高: {missing_authors}/{actual_total}")
        if missing_year / actual_total > 0.5:
            quality_issues.append(f"年份缺失率过高: {missing_year}/{actual_total}")
    if empty_topics > 0:
        quality_issues.append(f"{empty_topics} 个主题暂无论文")

    return {
        "new": new_count,
        "updated": updated_count,
        "total": actual_total,
        "topics_processed": topics_processed,
        "empty_topics": empty_topics,
        "quality": {
            "missing_authors": missing_authors,
            "missing_year": missing_year,
            "issues": quality_issues,
        },
    }
