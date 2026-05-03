from app.services.llm_service_base import BaseLLMService
from app.services.llm_prompt_builder import PromptBuilder


class ReadingNavigatorService(BaseLLMService):

    def __init__(self):
        super().__init__("阅读导航")

    def build_prompt(self, paper: dict) -> str:
        builder = PromptBuilder(
            role="计算机科学导论的助教",
            task_description="正在帮助一位大一本科生阅读经典论文",
        )
        builder.add_paper_context(paper)
        builder.add_constraint('"与已知知识的联系"要特别强调（例如：数学分析中的ε-δ定义和程序正确性证明的相似性）')
        builder.add_constraint("语言亲切自然，像学长在给你推荐论文")
        builder.add_constraint("不要用太多术语，如果用了必须解释")
        builder.add_constraint("core_concepts 最多 5 个即可，不要写太多")
        builder.add_constraint("discussion_questions 最多 3 个即可")
        builder.add_constraint("每个 explanation 控制在 50 字以内")
        builder.set_output_format({
            "why_read": "一段话说明为什么这篇论文值得读（启发大一学生的语气）",
            "core_concepts": [
                {"term": "概念名", "explanation": "用大一学生能懂的话解释", "importance": "core/supporting/background"}
            ],
            "background_notes": "需要哪些前置知识，用列表形式，每项包含知识名和为什么需要",
            "reading_tips": {
                "order": "建议的阅读顺序",
                "estimated_time": "预计阅读时间",
                "difficulty_hint": "哪里可能会卡住，怎么克服"
            },
            "discussion_questions": ["思考题1", "思考题2"]
        })
        return builder.build()


def generate_reading_navigator(paper: dict) -> dict:
    service = ReadingNavigatorService()
    return service.execute(paper=paper, max_tokens=4096)
