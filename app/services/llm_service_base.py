from abc import ABC, abstractmethod
from app.services.llm_utils import _call_llm, parse_llm_json_response


class BaseLLMService(ABC):

    def __init__(self, service_name: str):
        self.service_name = service_name

    @abstractmethod
    def build_prompt(self, **kwargs) -> str:
        pass

    def call_llm(self, prompt: str, max_tokens: int = None, enable_json_parsing: bool = True) -> tuple:
        messages = [{"role": "user", "content": prompt}]
        content, usage = _call_llm(messages, max_tokens=max_tokens)

        if enable_json_parsing:
            result = parse_llm_json_response(content, self.service_name)
        else:
            result = content

        return result, usage

    def execute(self, max_tokens: int = None, enable_json_parsing: bool = True, **kwargs) -> tuple:
        prompt = self.build_prompt(**kwargs)
        return self.call_llm(prompt, max_tokens=max_tokens, enable_json_parsing=enable_json_parsing)
