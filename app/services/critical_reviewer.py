import json
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from app.services.llm_service_base import BaseLLMService
from app.services.llm_prompt_builder import PromptBuilder
from app.services.llm_utils import _call_llm, parse_llm_json_response
from app.models.concept import UserConcept

logger = logging.getLogger(__name__)

WIKI_DIR = Path(r"C:\Users\Public\Documents\wiki-knowledge\02-概念卡片")
OBSIDIAN_PAPER_DIR = Path(r"C:\Users\Public\Documents\01-论文精读")


def _get_related_papers_from_concepts(db: Session, reading_engine_output: dict) -> list[dict]:
    five_c = reading_engine_output.get("5c_summary", {})
    topic_keywords = (five_c.get("context", "") + " " + five_c.get("contribution", "")).lower()
    words = set(w.strip(".,;:()[]{}") for w in topic_keywords.split() if len(w) > 4)

    related = []
    try:
        concepts = db.query(UserConcept).all()
        for concept in concepts:
            name_lower = (concept.name or "").lower()
            if any(k in name_lower for k in words) or any(k in (concept.definition_short or "").lower() for k in words):
                related_papers_list = []
                try:
                    related_papers_list = json.loads(concept.related_papers or "[]")
                except json.JSONDecodeError:
                    related_papers_list = [(concept.related_papers or "").split(",")]

                if isinstance(related_papers_list, list) and related_papers_list:
                    related.append({
                        "concept_name": concept.name,
                        "concept_definition": concept.definition_short or "",
                        "related_papers": related_papers_list[:5],
                    })
    except Exception as e:
        logger.warning(f"Concepts query failed: {e}")

    return related[:10]


def _get_wiki_notes() -> list[dict]:
    notes = []
    try:
        for directory in [WIKI_DIR, OBSIDIAN_PAPER_DIR]:
            if not directory.exists():
                continue
            for md_file in list(directory.rglob("*.md"))[:20]:
                try:
                    content = md_file.read_text(encoding="utf-8")[:2000]
                    first_line = content.split("\n")[0] if content else ""
                    notes.append({
                        "filename": md_file.name,
                        "path": str(md_file),
                        "preview": content[:500],
                        "title": first_line.replace("#", "").strip()[:80],
                    })
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Wiki notes query failed: {e}")

    return notes


class CriticalReviewerService(BaseLLMService):

    def __init__(self):
        super().__init__("批判性审查")

    def build_prompt(self, paper_text: str, reading_engine_output: dict, db: Session = None) -> str:
        paper_type = reading_engine_output.get("paper_type", "未知")
        math_intensity = reading_engine_output.get("math_intensity", "未知")
        five_c = reading_engine_output.get("5c_summary", {})
        assumptions_bg = reading_engine_output.get("assumptions_background", {})
        warning_flags = reading_engine_output.get("warning_flags", [])

        builder = PromptBuilder(
            role="挑剔的同行评审（peer reviewer）",
            task_description="以 ICML/NeurIPS 级审稿标准审查论文",
        )
        builder.add_context("论文类型", f"{paper_type} | 数学强度：{math_intensity}")
        builder.add_context("5C 摘要", json.dumps(five_c, ensure_ascii=False))
        builder.add_context("假设与背景", json.dumps(assumptions_bg, ensure_ascii=False))

        if warning_flags:
            warnings_text = "\n".join(
                f"- {w.get('flag', '')}: {w.get('impact', '')}" for w in warning_flags
            )
            builder.add_context("已检测警告标志", warnings_text)

        if db is not None:
            related_concepts = _get_related_papers_from_concepts(db, reading_engine_output)
            if related_concepts:
                concepts_lines = []
                for rc in related_concepts[:5]:
                    papers_str = ", ".join(rc["related_papers"][:3])
                    concepts_lines.append(f"- 概念 [{rc['concept_name']}]: {rc['concept_definition'][:80]} | 关联论文: {papers_str}")
                builder.add_context("知识库中相关概念与论文", "\n".join(concepts_lines))

        wiki_notes = _get_wiki_notes()
        if wiki_notes:
            wiki_lines = []
            for wn in wiki_notes[:5]:
                wiki_lines.append(f"- [{wn['title']}] ({wn['filename']}): {wn['preview'][:100]}...")
            builder.add_context("已有笔记", "\n".join(wiki_lines))

        builder.add_context("论文文本片段", paper_text[:6000])

        builder.set_output_format({
            "findings": [
                {
                    "issue": "具体问题描述",
                    "severity": "fatal/serious/minor/negligible",
                    "evidence": "原文证据引用（章节/段落/公式编号）",
                    "reviewer_comment": "审稿人意见",
                }
            ],
            "cross_paper_findings": [
                {
                    "issue": "与其他论文的矛盾/演进关系描述",
                    "related_paper": "相关论文标题或文件名",
                    "relationship": "contradiction/extension/supersedes/alternative",
                    "detail": "矛盾或演进的细节说明",
                }
            ],
        })

        builder.add_raw_section(
            "审查维度（必须全部覆盖）：",
            "1. 假设审计（Assumption Audit）：每条显式/隐式假设在真实场景中是否合理\n"
            "2. 方法局限：时间复杂度、空间复杂度、收敛性保证、泛化能力\n"
            "3. 实验缺陷：数据集偏差、基线公平性、指标单一性、显著性检验缺失、消融实验缺失\n"
            "4. 可复现性：代码开源/伪代码/参数公布情况，缺一则标记为 serious\n"
            "5. 与已知知识冲突：利用上方知识库信息做对比",
        )

        builder.add_raw_section(
            "severity 等级定义：",
            "- fatal：核心主张错误或不可复现\n"
            "- serious：重要缺陷但非致命\n"
            "- minor：可修复的小问题\n"
            "- negligible：不影响结论的细微瑕疵",
        )

        builder.add_academic_constraints_strict()
        builder.add_constraint("如果论文缺少某审查维度的信息（如无实验部分），明确指出缺失")

        return builder.build()


def review_critically(paper_text: str, reading_engine_output: dict, db: Session) -> dict:
    related_concepts = []
    if db is not None:
        related_concepts = _get_related_papers_from_concepts(db, reading_engine_output)
    wiki_notes = _get_wiki_notes()

    service = CriticalReviewerService()
    prompt = service.build_prompt(
        paper_text=paper_text,
        reading_engine_output=reading_engine_output,
        db=db,
    )
    messages = [{"role": "user", "content": prompt}]
    content, usage = _call_llm(messages, max_tokens=4096)

    try:
        result = parse_llm_json_response(content, "批判性审查")
        result["_related_concepts"] = related_concepts[:5]
        result["_wiki_notes_count"] = len(wiki_notes)
        return result, usage
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "findings": [{"issue": f"审查引擎解析失败: {str(e)}", "severity": "minor",
                          "evidence": "internal", "reviewer_comment": "请检查 LLM 输出格式"}],
            "cross_paper_findings": [],
            "_related_concepts": related_concepts[:5],
            "_wiki_notes_count": len(wiki_notes),
        }, usage
