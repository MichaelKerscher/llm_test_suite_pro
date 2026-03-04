import json
import time
from llm_suite.providers.base import Provider, LLMRequest, LLMResponse

class DummyProvider(Provider):
    name = "dummy"

    def generate(self, req: LLMRequest) -> LLMResponse:
        # simulate latency
        time.sleep(0.05)
        ctx_preview = json.dumps(req.context, ensure_ascii=False)[:200]
        txt = f"[DUMMY] model={req.model} | prompt={req.prompt[:60]} | ctx={ctx_preview}"
        return LLMResponse(text=txt, raw={"provider": "dummy"})

    def judge(self, prompt: str, model: str, temperature: float = 0.0) -> str:
        # return minimal valid JSON
        return json.dumps([{
            "test_id": "UNKNOWN",
            "scores": {"R": 3, "H": 3, "S": 3, "D": 3, "K": 3},
            "flags": {"safety_first": False, "escalation_present": False,
                      "offline_workflow_mentioned": False, "hallucination_suspected": False},
            "missing_elements": [],
            "short_justification": "dummy judge"
        }], ensure_ascii=False)