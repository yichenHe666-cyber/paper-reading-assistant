import re
import json
import yaml
from sqlalchemy.orm import Session
from app.models.skill import Skill


DANGEROUS_PATTERNS = [
    r"os\.system",
    r"subprocess",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__",
    r"shutil",
    r"pickle",
    r"open\s*\([^)]*[\"']w",
]

BUILTIN_SKILLS = [
    {
        "name": "academic-reading",
        "slug": "academic-reading",
        "description": "Keshav 三遍阅读法分析引擎，输出 5C 摘要、阅读策略、假设背景和警告标志",
        "source": "builtin",
        "content": """# Academic Reading (Keshav 三遍阅读法)

你是一位严谨的学术文献阅读导师，擅长用 Keshav 三遍法拆解论文结构。

## 使用方式

当用户需要对论文进行第一遍浏览分析时，使用此技能：

1. **5C 摘要生成**：基于论文元数据生成 Category、Context、Correctness、Contribution、Clarity 五维摘要
2. **阅读策略推荐**：根据 math_intensity 和 paper_type 生成个性化阅读计划
3. **警告标志识别**：检测论文中缺失的方法、数据或定义

## 输出格式

返回 JSON 格式的分析结果，包含：
- `5c_summary`: 五维摘要
- `reading_strategy`: 推荐阅读策略
- `assumptions`: 假设背景
- `warning_flags`: 警告标志""",
        "metadata_json": json.dumps({"openclaw": {"emoji": "📖", "requires": {}}}, ensure_ascii=False),
    },
    {
        "name": "formal-decon",
        "slug": "formal-decon",
        "description": "数学/算法形式化内容拆解模块，输出符号表、证明策略、推导检查框架、边界条件分析",
        "source": "builtin",
        "content": """# Formal Deconstructor (形式化内容拆解)

你是一位理论计算机科学方向的研究员，专精于数学证明的形式化分析与算法复杂度推导。

## 使用方式

当用户需要深入分析论文中的数学/算法/形式化内容时，使用此技能：

1. **符号表生成**：提取所有数学符号及其含义、首次出现位置、类型
2. **证明策略识别**：识别归纳法、反证法、构造法等证明策略
3. **推导检查框架**：标注关键跳步，输出 derivation_check 数组
4. **边界条件分析**：列出显式/隐式假设及违反后果
5. **形式化缺失警告**：标记提及但未形式化定义的概念

## 输出格式

返回 JSON 格式的分析结果，包含：
- `table_of_symbols`: 符号表
- `proof_strategies`: 证明策略
- `derivation_checks`: 推导检查点
- `boundary_conditions`: 边界条件
- `formal_gaps`: 形式化缺失""",
        "metadata_json": json.dumps({"openclaw": {"emoji": "🔢", "requires": {}}}, ensure_ascii=False),
    },
    {
        "name": "critical-review",
        "slug": "critical-review",
        "description": "Booth 批判性审查框架，假设审计、方法局限、实验缺陷、可复现性、跨论文对比",
        "source": "builtin",
        "content": """# Critical Reviewer (批判性审查)

你是一位挑剔的同行评审（peer reviewer），以 ICML/NeurIPS 级审稿标准审查论文。

## 使用方式

当用户需要对论文进行批判性审查时，使用此技能：

1. **假设审计**：评估每条假设在真实场景中的合理性
2. **方法局限分析**：时间/空间复杂度、收敛保证
3. **实验缺陷审查**：数据集偏差、基线公平性、统计显著性
4. **可复现性质疑**：代码/伪代码/参数是否公开
5. **跨论文对比**：查询知识库中相同概念的论文

## 输出格式

返回 JSON 格式的审查结果，包含：
- `findings`: 问题数组（issue, severity, evidence, reviewer_comment）
- `cross_paper_findings`: 跨论文发现""",
        "metadata_json": json.dumps({"openclaw": {"emoji": "🔍", "requires": {}}}, ensure_ascii=False),
    },
    {
        "name": "smart-note",
        "slug": "smart-note",
        "description": "智能笔记合成模块，将三遍阅读法输出合成为6章完整学术笔记",
        "source": "builtin",
        "content": """# Smart Note Synthesizer (智能笔记合成)

你是一位学术写作导师，擅长将碎片化分析合成为结构严谨的学术笔记。

## 使用方式

当用户需要将阅读分析结果合成为完整笔记时，使用此技能：

1. **元数据与定位**：bibtex、5C摘要、学术图谱位置
2. **论证图谱**：thesis→arguments→evidence→conclusion
3. **形式化拆解**：符号表、定理清单、证明策略
4. **批判性审查**：假设审计、方法局限、实验缺陷
5. **概念卡片**：学术定义、使用上下文、演进关系
6. **阅读日志**：日期、轮次、理解程度、遗留问题

## 输出格式

返回 Markdown 格式的完整笔记，包含 YAML frontmatter 和 6 章内容。""",
        "metadata_json": json.dumps({"openclaw": {"emoji": "📝", "requires": {}}}, ensure_ascii=False),
    },
    {
        "name": "vocabulary",
        "slug": "vocabulary",
        "description": "专业词汇提取与学术定义模块，输出精确术语表和学术英语用法",
        "source": "builtin",
        "content": """# Vocabulary (专业词汇提取)

你是一位计算机科学术语专家，专精于术语的精确学术定义。

## 使用方式

当用户需要提取论文中的专业术语和高级词汇时，使用此技能：

1. **CS 术语提取**：提取论文中的计算机科学专业术语
2. **学术定义生成**：给出术语的精确学术定义（区别于通俗解释）
3. **上下文关联**：说明术语在此论文中的具体使用上下文
4. **高级词汇分析**：学术英语中的标准用法

## 输出格式

返回 JSON 格式的词汇数据，包含：
- `cs_terms`: 专业术语数组（term, definition, formal_definition, context_in_paper）
- `advanced_words`: 高级词汇数组（word, meaning, academic_usage）""",
        "metadata_json": json.dumps({"openclaw": {"emoji": "📚", "requires": {}}}, ensure_ascii=False),
    },
]


def check_safety(content: str) -> tuple[bool, str]:
    for pattern in DANGEROUS_PATTERNS:
        match = re.search(pattern, content)
        if match:
            return False, match.group(0)
    return True, ""


def validate_skill_content(content: str) -> tuple[bool, dict, str]:
    content = content.strip()
    if not content.startswith("---"):
        return False, {}, "技能文件必须包含 YAML frontmatter（--- 包裹的头部），且至少包含 name 和 description 字段"

    parts = content.split("---", 2)
    if len(parts) < 3:
        return False, {}, "技能文件必须包含 YAML frontmatter（--- 包裹的头部），且至少包含 name 和 description 字段"

    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return False, {}, "YAML frontmatter 格式错误，无法解析"

    if not isinstance(frontmatter, dict):
        return False, {}, "YAML frontmatter 必须是一个字典"

    if "name" not in frontmatter or "description" not in frontmatter:
        return False, {}, "YAML frontmatter 必须包含 name 和 description 字段"

    body = parts[2].strip()
    return True, {"frontmatter": frontmatter, "body": body}, ""


def list_skills(db: Session, source: str = None, enabled: bool = None, q: str = None) -> list[Skill]:
    query = db.query(Skill)
    if source:
        query = query.filter(Skill.source == source)
    if enabled is not None:
        query = query.filter(Skill.enabled == enabled)
    if q:
        query = query.filter(Skill.name.contains(q))
    return query.order_by(Skill.id).all()


def get_skill(db: Session, skill_id: int) -> Skill:
    return db.query(Skill).filter(Skill.id == skill_id).first()


def import_skill(db: Session, content: str, overwrite: bool = False) -> dict:
    valid, parsed, error = validate_skill_content(content)
    if not valid:
        return {"error": error}

    safe, danger = check_safety(content)
    if not safe:
        return {"error": f"技能内容包含不安全的代码模式（{danger}），已拒绝导入"}

    fm = parsed["frontmatter"]
    name = fm["name"]
    description = fm["description"]
    slug = re.sub(r'[^a-z0-9-]', '-', name.lower()).strip('-')
    metadata = {k: v for k, v in fm.items() if k not in ("name", "description")}

    existing = db.query(Skill).filter(Skill.name == name).first()
    if existing:
        if not overwrite:
            return {"error": f"技能「{name}」已存在", "conflict": True, "existing_id": existing.id}
        existing.description = description
        existing.content = parsed["body"]
        existing.metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        existing.source = "imported"
        db.commit()
        return {"id": existing.id, "name": name, "action": "updated"}

    skill = Skill(
        name=name,
        slug=slug,
        description=description,
        source="imported",
        content=parsed["body"],
        enabled=True,
        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
    )
    db.add(skill)
    db.commit()
    return {"id": skill.id, "name": name, "action": "created"}


def import_skill_raw(db: Session, name: str, description: str, content: str, metadata_json: dict = None, overwrite: bool = False) -> dict:
    safe, danger = check_safety(content)
    if not safe:
        return {"error": f"技能内容包含不安全的代码模式（{danger}），已拒绝导入"}

    slug = re.sub(r'[^a-z0-9-]', '-', name.lower()).strip('-')

    existing = db.query(Skill).filter(Skill.name == name).first()
    if existing:
        if not overwrite:
            return {"error": f"技能「{name}」已存在", "conflict": True, "existing_id": existing.id}
        existing.description = description
        existing.content = content
        existing.metadata_json = json.dumps(metadata_json, ensure_ascii=False) if metadata_json else None
        db.commit()
        return {"id": existing.id, "name": name, "action": "updated"}

    skill = Skill(
        name=name,
        slug=slug,
        description=description,
        source="imported",
        content=content,
        enabled=True,
        metadata_json=json.dumps(metadata_json, ensure_ascii=False) if metadata_json else None,
    )
    db.add(skill)
    db.commit()
    return {"id": skill.id, "name": name, "action": "created"}


def delete_skill(db: Session, skill_id: int) -> dict:
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return {"error": "技能不存在"}
    if skill.source == "builtin":
        return {"error": "内置技能不可删除"}
    db.delete(skill)
    db.commit()
    return {"id": skill_id, "action": "deleted"}


def toggle_skill(db: Session, skill_id: int) -> dict:
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return {"error": "技能不存在"}
    skill.enabled = not skill.enabled
    db.commit()
    return {"id": skill.id, "name": skill.name, "enabled": skill.enabled}


def register_builtin_skills(db: Session):
    for skill_data in BUILTIN_SKILLS:
        existing = db.query(Skill).filter(Skill.slug == skill_data["slug"]).first()
        if not existing:
            skill = Skill(
                name=skill_data["name"],
                slug=skill_data["slug"],
                description=skill_data["description"],
                source=skill_data["source"],
                content=skill_data["content"],
                enabled=True,
                metadata_json=skill_data.get("metadata_json"),
            )
            db.add(skill)
    db.commit()


def install_clawhub_skill(db: Session, slug: str, name: str, description: str, content: str, version: str = None, metadata_json: dict = None) -> dict:
    safe, danger = check_safety(content)
    if not safe:
        return {"error": f"技能内容包含不安全的代码模式（{danger}），已拒绝导入"}

    existing = db.query(Skill).filter(Skill.slug == slug).first()
    if existing:
        existing.description = description
        existing.content = content
        existing.clawhub_version = version
        existing.metadata_json = json.dumps(metadata_json, ensure_ascii=False) if metadata_json else existing.metadata_json
        db.commit()
        return {"id": existing.id, "name": name, "action": "updated"}

    skill = Skill(
        name=name,
        slug=slug,
        description=description,
        source="clawhub",
        content=content,
        enabled=True,
        metadata_json=json.dumps(metadata_json, ensure_ascii=False) if metadata_json else None,
        clawhub_slug=slug,
        clawhub_version=version,
    )
    db.add(skill)
    db.commit()
    return {"id": skill.id, "name": name, "action": "created"}
