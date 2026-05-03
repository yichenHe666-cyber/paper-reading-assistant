import json
from datetime import date
from app.services.llm_service_base import BaseLLMService
from app.services.llm_prompt_builder import PromptBuilder


def _strip_code_block(content: str) -> str:
    if content.startswith("```markdown"):
        return "\n".join(content.split("\n")[1:-1])
    elif content.startswith("```"):
        return "\n".join(content.split("\n")[1:-1])
    return content


class SmartNoteSynthesizerService(BaseLLMService):

    def __init__(self):
        super().__init__("智能笔记合成")

    def build_prompt(
        self,
        paper: dict,
        reading_engine_output: dict,
        formal_decon_output: dict,
        critical_review_output: dict,
        full_text: str = "",
    ) -> str:
        today = str(date.today())
        title = paper.get("title", "Untitled")
        authors = paper.get("authors", "[]")
        year = paper.get("year", "")
        venue = paper.get("venue", "") or ""
        topic = paper.get("topic_id", "").replace("_", " ")
        doi = paper.get("doi", "") or ""
        paper_type = reading_engine_output.get("paper_type", "未知")
        math_intensity = reading_engine_output.get("math_intensity", "未知")
        five_c = reading_engine_output.get("5c_summary", {})
        reading_strategy = reading_engine_output.get("reading_strategy", {})
        assumptions_bg = reading_engine_output.get("assumptions_background", {})
        warning_flags = reading_engine_output.get("warning_flags", [])

        symbol_table = formal_decon_output.get("symbol_table", [])
        theorems = formal_decon_output.get("theorems", [])
        derivation_checks = formal_decon_output.get("derivation_checks", [])
        boundary_conditions = formal_decon_output.get("boundary_conditions", [])
        formal_gaps = formal_decon_output.get("formal_gaps", [])

        findings = critical_review_output.get("findings", [])
        cross_paper_findings = critical_review_output.get("cross_paper_findings", [])

        bibtex_authors = ""
        try:
            auth_list = json.loads(authors) if isinstance(authors, str) else authors
            if isinstance(auth_list, list) and auth_list:
                bibtex_authors = " and ".join(auth_list)
        except (json.JSONDecodeError, TypeError):
            bibtex_authors = authors

        five_c_json = json.dumps(five_c, ensure_ascii=False, indent=2)
        warnings_json = json.dumps(warning_flags, ensure_ascii=False, indent=2)
        strategy_json = json.dumps(reading_strategy, ensure_ascii=False, indent=2)
        assumptions_json = json.dumps(assumptions_bg, ensure_ascii=False, indent=2)
        symbols_json = json.dumps(symbol_table, ensure_ascii=False, indent=2)
        theorems_json = json.dumps(theorems, ensure_ascii=False, indent=2)
        derivations_json = json.dumps(derivation_checks, ensure_ascii=False, indent=2)
        boundaries_json = json.dumps(boundary_conditions, ensure_ascii=False, indent=2)
        gaps_json = json.dumps(formal_gaps, ensure_ascii=False, indent=2)
        findings_json = json.dumps(findings, ensure_ascii=False, indent=2)
        cross_json = json.dumps(cross_paper_findings, ensure_ascii=False, indent=2)

        bibtex_block = (
            "@article{paper,\n"
            f"  title = {{{title}}},\n"
            f"  author = {{{bibtex_authors}}},\n"
            f"  year = {{{year}}},\n"
            f"  journal = {{{venue}}},\n"
            f"  doi = {{{doi}}}\n"
            "}"
        )

        builder = PromptBuilder(
            role="学术写作导师",
            task_description="擅长将碎片化分析合成为结构严谨的学术笔记",
        )
        builder.add_context("论文", title)
        builder.add_context("作者", authors)
        builder.add_context("年份", year)
        builder.add_context("刊物", venue)
        builder.add_context("主题", topic)
        builder.add_context("DOI", doi)
        builder.add_context("类型", paper_type)
        builder.add_context("数学强度", math_intensity)

        builder.add_raw_section(
            "## 输入数据",
            f"### 第一遍分析 (5C + 阅读策略)\n"
            f"五C摘要：{five_c_json}\n"
            f"阅读策略：{strategy_json}\n"
            f"假设背景：{assumptions_json}\n"
            f"警告标志：{warnings_json}\n\n"
            f"### 形式化拆解\n"
            f"符号表：{symbols_json}\n"
            f"定理清单：{theorems_json}\n"
            f"推导检查点：{derivations_json}\n"
            f"边界条件：{boundaries_json}\n"
            f"形式化缺失：{gaps_json}\n\n"
            f"### 批判性审查\n"
            f"审查发现：{findings_json}\n"
            f"跨论文发现：{cross_json}\n\n"
            f"### 论文原文片段\n"
            f"{full_text[:3000] if full_text else '（无全文文本）'}",
        )

        template = f"""---
type: paper
source: papers-we-love
topic: {topic}
paper_type: {paper_type}
math_intensity: {math_intensity}
authors: {authors}
year: {year}
venue: "{venue}"
doi: "{doi}"
read_status: 精读中
difficulty: {paper.get('difficulty', '中等')}
rating:
created: {today}
last_read: {today}
tags: []
---

# {title}

## 1. 元数据与定位

### BibTeX
```bibtex
{bibtex_block}
```

### 5C 摘要
- **Category（类别）**: [填写]
- **Context（背景）**: [填写]
- **Correctness（核心主张）**: [填写]
- **Contribution（贡献）**: [填写]
- **Clarity（写作质量）**: [填写]

### 在学术图谱中的位置
[说明该论文在其研究领域中的位置：与哪些经典工作构成对话，处于什么发展阶段]

## 2. 论证图谱

### 核心论点 (Thesis)
[论文的核心主张，用一句话表述]

### 主论证链
[从前提/假设 → 核心论证 → 支持的证据/实验 → 结论，以箭头或列表表示论证逻辑链条]

### 关键证据评估
[评估论文用以支撑主张的证据强度]

## 3. 形式化拆解

### 符号表
[从符号表数据生成表格]

### 定理与证明策略
[列出每个定理及其证明策略类型]

### 需手动推导的跳步
[列出 derivation_checks，每项包含 my_derivation 留空字段]

### 边界条件
[显式与隐式假设及违反后果]

### 形式化缺失警告
[列出 formal_gaps]

## 4. 批判性审查

### 假设审计
[评估每条假设的合理性]

### 方法与实验局限
[方法复杂度、收敛性等问题 | 实验设计缺陷]

### 可复现性评估
[代码开源情况、伪代码完整性、参数公开情况]

### 审稿人意见摘要
[列出所有 findings，按严重程度排序]

### 跨论文对比发现
[列出 cross_paper_findings]

## 5. 概念卡片

[为每个核心概念生成一张卡片，包含：学术定义、使用上下文、与本论文的具体关联、在概念演进中的位置]

## 6. 阅读日志

| 日期 | 轮次 | 理解程度 | 用时 | 遗留问题 | 下一步计划 |
|------|------|---------|------|---------|-----------|
| {today} | R3 | ⬜ 初步 ⬜ 一般 ⬜ 深入 | | | |

---

*由学术论文精读助手生成 | 方法论: Keshav 三遍法 + Booth 批判审查框架*"""

        builder.add_raw_section(
            "请严格按以下模板输出完整的 Markdown 笔记（包括 YAML frontmatter）：",
            template,
        )

        builder.add_academic_constraints()
        builder.add_constraint("上述大纲中的 [填写] 必须替换为实际分析内容，不得保留占位符")
        builder.add_constraint("所有填写的 derivations 的 my_derivation 字段必须留空（空字符串）")

        return builder.build()


def synthesize_note(
    paper: dict,
    reading_engine_output: dict,
    formal_decon_output: dict,
    critical_review_output: dict,
    full_text: str = "",
) -> tuple[str, dict]:
    service = SmartNoteSynthesizerService()
    content, usage = service.execute(
        paper=paper,
        reading_engine_output=reading_engine_output,
        formal_decon_output=formal_decon_output,
        critical_review_output=critical_review_output,
        full_text=full_text,
        max_tokens=6000,
        enable_json_parsing=False,
    )
    return _strip_code_block(content), usage
