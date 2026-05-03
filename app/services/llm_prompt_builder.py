import json


ACADEMIC_CONSTRAINTS = [
    "不要夸奖论文，只客观分析",
    "不要简化数学定义，保持原文的形式化严格性",
    "必须引用原文位置（摘要句子/章节号/公式编号/页码）",
    "不要使用比喻或通俗类比替代精确表述",
    "禁止提及'同学'、'Hello World'、'读心术'等科普化表述",
    "读者面向：数学系本科一年级，具备数学分析/高等代数/基础概率论背景",
]

ACADEMIC_CONSTRAINTS_STRICT = [
    "不要夸奖论文，只找问题",
    "不要简化数学定义，保持原文的形式化严格性",
    "必须引用原文位置（章节号/公式编号/页码）",
    "不要使用比喻或通俗类比替代精确表述",
    "禁止出现'同学'、'Hello World'、'读心术'等科普化表述",
    "读者面向：数学系本科一年级，具备数学分析/高等代数/基础概率论背景",
]


class PromptBuilder:

    def __init__(self, role: str, task_description: str):
        self.role = role
        self.task_description = task_description
        self.context_items = []
        self.output_format_spec = None
        self.output_format_label = "请以JSON格式返回（不要markdown代码块，只返回JSON）："
        self.constraints = []
        self.raw_sections = []

    def add_context(self, key: str, value: str):
        self.context_items.append((key, value))
        return self

    def add_paper_context(self, paper: dict):
        mappings = [
            ("论文标题", "title"),
            ("作者", "authors"),
            ("年份", "year"),
            ("摘要", "abstract"),
            ("刊物", "venue"),
            ("DOI", "doi"),
            ("主题领域", "topic_id"),
            ("子主题", "subtopic"),
        ]
        defaults = {"abstract": "无摘要"}
        for label, key in mappings:
            val = paper.get(key, "")
            if not val and key in defaults:
                val = defaults[key]
            if val:
                self.context_items.append((label, val))
        return self

    def set_output_format(self, format_spec: dict, label: str = None):
        self.output_format_spec = format_spec
        if label is not None:
            self.output_format_label = label
        return self

    def add_constraint(self, constraint: str):
        self.constraints.append(constraint)
        return self

    def add_academic_constraints(self):
        self.constraints.extend(ACADEMIC_CONSTRAINTS)
        return self

    def add_academic_constraints_strict(self):
        self.constraints.extend(ACADEMIC_CONSTRAINTS_STRICT)
        return self

    def add_raw_section(self, title: str, content: str):
        self.raw_sections.append((title, content))
        return self

    def build(self) -> str:
        parts = []

        parts.append(f"你是一位{self.role}，{self.task_description}")
        parts.append("")

        if self.context_items:
            for label, value in self.context_items:
                parts.append(f"{label}：{value}")
            parts.append("")

        if self.output_format_spec is not None:
            parts.append(self.output_format_label)
            parts.append("")
            parts.append(json.dumps(self.output_format_spec, ensure_ascii=False, indent=2))
            parts.append("")

        for title, content in self.raw_sections:
            if title:
                parts.append(title)
            parts.append(content)
            parts.append("")

        if self.constraints:
            parts.append("严格约束：")
            for c in self.constraints:
                parts.append(f"- {c}")
            parts.append("")

        return "\n".join(parts)
