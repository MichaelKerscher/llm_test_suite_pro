from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass
class TestCase:
    testcase_id: str
    incident_id: str
    context_level: str
    strategy: str
    user_message: str
    context_json: Dict[str, Any]

@dataclass
class LLMResult:
    testcase_id: str
    incident_id: str
    context_level: str
    strategy: str
    user_message: str
    context_json: Dict[str, Any]
    answer: str
    runtime_s: float
    judge: Optional[Dict[str, Any]] = None
    error: Optional[str] = None