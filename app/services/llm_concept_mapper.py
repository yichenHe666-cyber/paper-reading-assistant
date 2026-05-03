import json
from app.services.llm_service_base import BaseLLMService
from app.services.llm_prompt_builder import PromptBuilder


class ConceptMapperService(BaseLLMService):

    def __init__(self):
        super().__init__("概念映射")

    def build_prompt(self, paper: dict, navigator: dict) -> str:
        concepts = navigator.get("core_concepts", [])
        concepts_text = json.dumps(concepts, ensure_ascii=False)

        builder = PromptBuilder(
            role="计算机科学导论助教",
            task_description="正在帮助大一本科生建立概念知识库",
        )
        builder.add_context("论文标题", paper.get("title", ""))
        builder.add_context("论文的核心概念", concepts_text)
        builder.add_constraint("语言亲切自然，像学长在解释概念")
        builder.add_constraint("如果概念可以用数学类比（比如程序状态类比函数映射），一定要写出来")
        builder.add_constraint("每个概念的 related_concepts 至少写 2 个，方便 Obsidian 图谱连线")
        builder.add_constraint("每个概念都要包含与本篇论文的关联")
        builder.add_constraint("definition 控制在 80 字以内")
        builder.set_output_format(
            [
                {
                    "name": "概念的中文或英文名",
                    "name_en": "英文原名",
                    "category": "所属类别（如：程序验证 / 分布式系统 / 编程语言 等）",
                    "definition": "用大一学生能理解的话下定义（2-3句话）",
                    "one_sentence": "一句话理解（最精炼的概括）",
                    "related_papers": ["这篇论文的标题"],
                    "related_concepts": ["相关概念1", "相关概念2"],
                    "difficulty": "简单/中等/困难",
                }
            ],
            label="请为每个概念生成一张\"概念卡片\"，以 JSON 数组格式返回（只返回 JSON，不要代码块）：",
        )
        return builder.build()


def generate_concept_cards(paper: dict, navigator: dict) -> list[dict]:
    concepts = navigator.get("core_concepts", [])
    if not concepts:
        return [], None

    service = ConceptMapperService()
    return service.execute(paper=paper, navigator=navigator, max_tokens=4096)
