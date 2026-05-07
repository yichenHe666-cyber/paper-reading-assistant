import json
from app.services.llm_service_base import BaseLLMService
from app.services.llm_prompt_builder import PromptBuilder
from app.services.memory_engine import memory_engine
from app.database.session import SessionLocal


def _infer_paper_type(title: str, abstract: str) -> str:
    title_lower = (title or "").lower()
    abstract_lower = (abstract or "").lower()
    combined = title_lower + " " + abstract_lower

    survey_keywords = ["survey", "review", "a study of", "state of the art", "comprehensive", "taxonomy"]
    if any(k in combined for k in survey_keywords):
        return "综述"

    empirical_keywords = ["experiment", "evaluation", "benchmark", "dataset", "empirical", "measurement",
                          "performance", "compared", "results show", "we evaluate", "we test"]
    algo_keywords = ["algorithm", "complexity", "runtime", "polynomial", "approximation", "heuristic",
                     "optimization", "search", "scheduling", "caching"]

    theory_keywords = ["theorem", "proof", "lemma", "corollary", "proposition", "bound", "lower bound",
                       "upper bound", "asymptotic", "convergence", "guarantee", "optimal",
                       "necessary condition", "sufficient condition", "prove", "shows that"]

    theory_score = sum(1 for k in theory_keywords if k in combined)
    empirical_score = sum(1 for k in empirical_keywords if k in combined)
    algo_score = sum(1 for k in algo_keywords if k in combined)

    if theory_score >= 2 and theory_score >= empirical_score:
        return "理论"
    if algo_score >= 2 and algo_score > empirical_score:
        return "算法"
    if empirical_score >= 2:
        return "实证"
    return "理论"


def _infer_math_intensity(title: str, abstract: str) -> str:
    combined = ((title or "") + " " + (abstract or "")).lower()

    high_math = ["theorem", "proof", "lemma", "bound", "convergence", "probability", "measure",
                 "manifold", "topology", "group", "ring", "field", "banach", "hilbert",
                 "stochastic", "martingale", "differential equation", "functional",
                 "eigenvalue", "spectral", "norm", "convex", "gradient", "jacobian"]
    medium_math = ["optimization", "objective function", "gradient", "hessian", "matrix",
                   "vector", "linear algebra", "statistical", "hypothesis test",
                   "confidence interval", "regression", "classification", "bayesian",
                   "graph theory", "tree", "discrete", "set", "partition"]
    low_math = ["algorithm", "complexity", "data structure", "probability", "expected",
                "worst-case", "average-case", "random", "distribution"]

    high_count = sum(1 for k in high_math if k in combined)
    medium_count = sum(1 for k in medium_math if k in combined)
    low_count = sum(1 for k in low_math if k in combined)

    if high_count >= 2:
        return "高"
    if medium_count >= 2:
        return "中"
    if low_count >= 2:
        return "低"
    return "无"


def _detect_warning_flags(paper: dict, abstract: str) -> list[dict]:
    flags = []
    abstract_lower = (abstract or "").lower()

    if not paper.get("abstract"):
        flags.append({"flag": "无摘要", "evidence": "paper.abstract 为空", "impact": "无法进行第一遍浏览"})

    if not paper.get("authors") or paper.get("authors") in ("[]", '["Unknown"]'):
        flags.append({"flag": "作者信息缺失", "evidence": "paper.authors 缺失或为 Unknown", "impact": "无法评估作者学术背景"})

    method_keywords = ["method", "approach", "framework", "algorithm", "design", "propose"]
    has_method = any(k in abstract_lower for k in method_keywords)
    if paper.get("abstract") and not has_method:
        flags.append({"flag": "摘要中未描述方法", "evidence": "摘要文本中无方法相关关键词",
                      "impact": "第一遍浏览难以判断技术方案"})

    return flags


class AcademicReadingEngineService(BaseLLMService):

    def __init__(self):
        super().__init__("学术阅读引擎")

    def build_prompt(self, paper: dict, table_of_contents: str = None) -> str:
        paper_type = _infer_paper_type(paper.get("title", ""), paper.get("abstract", ""))
        math_intensity = _infer_math_intensity(paper.get("title", ""), paper.get("abstract", ""))

        builder = PromptBuilder(
            role="严谨的学术文献阅读导师",
            task_description="擅长用 Keshav 三遍法拆解论文结构",
        )
        builder.add_paper_context(paper)
        builder.add_context("已自动推断", f"paper_type={paper_type}, math_intensity={math_intensity}")

        db = SessionLocal()
        try:
            paper_id = paper.get("id")
            memory_segment = memory_engine.recall_for_context(db, paper_id=paper_id, call_type="academic_reading")
            if memory_segment:
                builder.inject_memory(memory_segment)
        finally:
            db.close()

        if table_of_contents:
            builder.add_context("目录结构", table_of_contents)

        builder.set_output_format({
            "paper_type": paper_type,
            "math_intensity": math_intensity,
            "5c_summary": {
                "category": "论文类型归类（如：理论分析论文 / 实验评估论文 / 综述 / 立场论文）",
                "context": "该论文所处的学术背景和问题域（50-100字），必须引用摘要中原文语句",
                "correctness": "该论文的核心主张/定理/结论（30-50字），如果有定理则给出定理编号",
                "contribution": "相对于已有工作，本文的具体贡献（30-50字），区分增量贡献 vs 突破贡献",
                "clarity": "写作质量评估（清晰/一般/晦涩），附带1句评价依据",
            },
            "reading_strategy": {
                "order": "建议的章节阅读顺序（例如：§3 方法 → §1 引言 → §4 实验 → §2 相关工作）",
                "focus": "第一遍后确定的核心阅读重点（具体到哪些段落/公式/图表）",
                "estimated_time": "预计第二遍精读所需时间（分钟），区分 paper_type",
                "skip_or_read": "read（值得精读）或 skip（建议跳过），附1句理由",
            },
            "assumptions_background": {
                "prerequisites": ["前置知识1（如测度论基础）", "前置知识2（如凸优化）"],
                "theory_background": "论文依赖的理论框架和假设背景（50-80字）",
            },
            "warning_flags": [
                {"flag": "具体警告", "evidence": "原文中证据位置", "impact": "对阅读/评估的影响"}
            ],
            "reading_plan": {
                "phase": "第一遍浏览",
                "duration_minutes": "第一遍预计时间",
                "actions": ["步骤1（5min）：读摘要和结论", "步骤2（10min）：浏览图表和章节标题"],
            },
        })

        builder.add_academic_constraints()
        builder.add_constraint("如果摘要不足，明确标注，不要臆造内容")
        builder.add_constraint("warning_flags 必须包含启发式检测到的实际标志")

        return builder.build()


def analyze_first_pass(paper: dict, table_of_contents: str = None) -> dict:
    service = AcademicReadingEngineService()
    return service.execute(paper=paper, table_of_contents=table_of_contents, max_tokens=4096)
