import json
from sqlalchemy.orm import Session
from app.services.llm_service_base import BaseLLMService
from app.services.llm_prompt_builder import PromptBuilder
from app.models.word_occurrence import WordOccurrence
from sqlalchemy import func


class VocabularyService(BaseLLMService):

    def __init__(self):
        super().__init__("词汇提取")

    def build_prompt(self, paper: dict) -> str:
        builder = PromptBuilder(
            role="计算机科学术语专家",
            task_description="专精于术语的精确学术定义",
        )
        builder.add_context("论文标题", paper.get("title", ""))
        builder.add_context("作者", paper.get("authors", ""))
        builder.add_context("摘要", paper.get("abstract", "无摘要"))

        builder.set_output_format({
            "cs_terms": [
                {
                    "word": "术语原文",
                    "phonetic": "/IPA音标/",
                    "meaning_cn": "中文对应术语",
                    "formal_definition": "该术语在计算机科学文献中的标准学术定义（50-80字），必须区别于通俗解释",
                    "context_in_paper": "该术语在此论文中的具体使用上下文和含义（30-50字），引用原文位置",
                    "collocations": ["专业搭配1", "专业搭配2"],
                    "sentence": "论文中使用该词的原文例句",
                }
            ],
            "advanced_words": [
                {
                    "word": "词汇",
                    "phonetic": "/IPA音标/",
                    "meaning_cn": "中文含义",
                    "academic_usage": "该词汇在学术英语中的标准用法和语义场（20-40字）",
                    "collocations": ["学术搭配1", "学术搭配2"],
                    "sentence": "论文中的例句",
                }
            ],
        })

        builder.add_raw_section(
            "分类标准：",
            "- cs_terms：计算机科学领域的专业术语（如 algorithm, invariant, syntax, semantics, concurrency, deadlock, axiom, precondition, stationary distribution, eigenvalue, convexity 等）\n"
            "- advanced_words：超出高中英语大纲的学术词汇（如 consequence, deduce, arbitrary, rigorous, subsequent, explicit, monotonic, asymptotic, tractable, intractable 等），注意不要收录高考考纲内的基础词汇",
        )

        builder.add_constraint("每类最多提取 8 个词")
        builder.add_constraint("音标使用 IPA 国际音标")
        builder.add_constraint("例句必须来自论文原文")
        builder.add_constraint("cs_terms 侧重学术定义，不要给出通俗解释")
        builder.add_constraint("两类不要有重复的单词")
        builder.add_constraint("sentence 控制在 30 个英文单词以内")
        builder.add_constraint("formal_definition 必须具有学术深度，可引用标准教科书定义")
        builder.add_constraint("面向读者：数学系本科一年级，具备数学分析/高等代数/基础概率论背景")
        builder.add_constraint("不要给出\"通俗易懂\"的解释")
        builder.add_constraint("不要使用比喻或日常类比")
        builder.add_constraint("禁止提及\"同学\"、\"Hello World\"、\"读心术\"等科普化表述")

        return builder.build()


def extract_vocabulary(paper: dict) -> tuple[dict, dict]:
    service = VocabularyService()
    result, usage = service.execute(paper=paper, max_tokens=4096)

    for term in result.get("cs_terms", []):
        if "formal_definition" not in term:
            term["formal_definition"] = term.get("meaning_cn", "")
        if "context_in_paper" not in term:
            term["context_in_paper"] = ""

    for word in result.get("advanced_words", []):
        if "academic_usage" not in word:
            word["academic_usage"] = word.get("meaning_cn", "")

    return result, usage


def apply_dedup(db: Session, paper_id: str, raw_words: dict) -> dict:
    result = {"cs_terms": [], "advanced_words": []}

    for word in raw_words.get("cs_terms", []):
        count = db.query(func.count(WordOccurrence.id)).filter(
            WordOccurrence.word == word["word"],
            WordOccurrence.word_type == "cs_term",
        ).scalar()
        if count < 2:
            result["cs_terms"].append(word)
            existing = db.query(WordOccurrence).filter(
                WordOccurrence.word == word["word"],
                WordOccurrence.paper_id == paper_id,
            ).first()
            if not existing:
                db.add(WordOccurrence(word=word["word"], word_type="cs_term", paper_id=paper_id))

    for word in raw_words.get("advanced_words", []):
        count = db.query(func.count(WordOccurrence.id)).filter(
            WordOccurrence.word == word["word"],
            WordOccurrence.word_type == "advanced",
        ).scalar()
        if count < 2:
            result["advanced_words"].append(word)
            existing = db.query(WordOccurrence).filter(
                WordOccurrence.word == word["word"],
                WordOccurrence.paper_id == paper_id,
            ).first()
            if not existing:
                db.add(WordOccurrence(word=word["word"], word_type="advanced", paper_id=paper_id))

    db.commit()
    return result


def build_vocabulary_markdown(paper: dict, vocabulary: dict) -> str:
    cs_terms = vocabulary.get("cs_terms", [])
    advanced_words = vocabulary.get("advanced_words", [])

    md = f"""---
type: vocabulary
paper: "{paper.get('title', '')}"
topic: {paper.get('topic_id', '')}
created: {paper.get('_now', '')}
---

# {paper.get('title', '')} — 专业词汇

## 🔬 计算机专业词汇

| 单词 | 音标 | 中文术语 | 学术定义 | 本论文上下文 | 专业搭配 | 原文例句 |
|------|------|---------|---------|-----------|---------|---------|
"""
    for w in cs_terms:
        coll = ", ".join(w.get("collocations", [])[:2])
        formal_def = (w.get("formal_definition", w.get("meaning_cn", "")))[:60]
        context = (w.get("context_in_paper", ""))[:50]
        md += f"| {w['word']} | {w.get('phonetic', '')} | {w.get('meaning_cn', '')} | {formal_def} | {context} | {coll} | {w.get('sentence', '')} |\n"

    md += "\n## 📖 进阶学术词汇\n\n"
    md += "| 单词 | 音标 | 中文 | 学术用法 | 常见搭配 | 原文例句 |\n"
    md += "|------|------|------|---------|---------|---------|\n"

    for w in advanced_words:
        coll = ", ".join(w.get("collocations", [])[:2])
        acad_usage = (w.get("academic_usage", w.get("meaning_cn", "")))[:50]
        md += f"| {w['word']} | {w.get('phonetic', '')} | {w.get('meaning_cn', '')} | {acad_usage} | {coll} | {w.get('sentence', '')} |\n"

    md += f"\n---\n*由经典论文精读助手生成*\n"
    return md
