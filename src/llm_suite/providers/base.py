from dataclasses import dataclass
from typing import Any, Dict, Optional, List

@dataclass
class LLMRequest:
    model: str
    prompt: str
    context: Dict[str, Any]
    temperature: float = 0.2
    input_type: str = "text"
    media: Optional[Dict[str, str]] = None

@dataclass
class LLMResponse:
    text: str
    raw: Dict[str, Any] | None = None

class Provider:
    name: str = "base"
    def generate(self, req: LLMRequest) -> LLMResponse:
        raise NotImplementedError
    def judge(self, prompt: str, model: str, temperature: float = 0.0) -> str:
        raise NotImplementedError