import json
import httpx
from llm_suite.config import ProviderCfg
from llm_suite.providers.base import Provider, LLMRequest, LLMResponse

def _append_context_to_prompt(prompt: str, context: dict | None) -> str:
    if not context:
        return prompt
    ctx_str = json.dumps(context, ensure_ascii=False, sort_keys=True, indent=2)
    return prompt + "\n\n[CONTEXT_JSON]\n<<<\n" + ctx_str + "\n>>>\n"

class Provider506(Provider):
    name = "provider_506"

    def __init__(self, cfg: ProviderCfg):
        self.cfg = cfg
        if not self.cfg.base_url:
            # allow COMPANYGPT_BASE_URL to be used as LLM_BASE_URL for convenience
            raise ValueError("LLM_BASE_URL is required for provider_506 (e.g., https://companygpt.506.ai:3003)")
        if not self.cfg.org_id or not self.cfg.api_key:
            raise ValueError("COMPANYGPT_ORG_ID and COMPANYGPT_API_KEY are required for provider_506")

        self.base = self.cfg.base_url.rstrip("/")

        self.headers_auth = {
            "api-organization-id": self.cfg.org_id,
            "api-key": self.cfg.api_key,
        }
        self.headers_json = {
            **self.headers_auth,
            "Content-Type": "application/json",
        }

        self.timeout = httpx.Timeout(self.cfg.timeout_s)

    def _chat_no_stream(
        self,
        *,
        model_id: str,
        prompt: str,
        temperature: float,
        selected_mode: str,
        assistant_id: str | None,
        internal_system_prompt: bool,
    ) -> str:
        url = f"{self.base}/api/v1/public/chatNoStream"

        params = {"internalSystemPrompt": "true" if internal_system_prompt else "false"}

        payload = {
            "model": {"id": model_id},
            "messages": [{"role": "user", "content": prompt, "references": [], "sources": []}],
            "roleId": "",
            "temperature": temperature,
            "selectedMode": selected_mode,
            "selectedFiles": [],
            "selectedDataCollections": [],
        }
        if assistant_id:
            payload["selectedAssistantId"] = assistant_id

        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, headers=self.headers_json, params=params, json=payload)
            r.raise_for_status()
            data = r.json()
            return (data.get("content") or "").strip()

    def generate(self, req: LLMRequest) -> LLMResponse:
        prompt = _append_context_to_prompt(req.prompt, req.context)

        txt = self._chat_no_stream(
            model_id=req.model,
            prompt=prompt,
            temperature=req.temperature,
            selected_mode=self.cfg.default_mode,
            assistant_id=self.cfg.generator_assistant_id or None,
            internal_system_prompt=self.cfg.internal_system_prompt,
        )
        return LLMResponse(text=txt, raw={"provider": "provider_506"})

    def judge(self, prompt: str, model: str, temperature: float = 0.0) -> str:
        txt = self._chat_no_stream(
            model_id=model,
            prompt=prompt,
            temperature=temperature,
            selected_mode=self.cfg.default_mode,
            assistant_id=self.cfg.judge_assistant_id or None,
            internal_system_prompt=False,
        )
        # strip simple code fences if provider returns ```json ... ```
        t = txt.strip()
        if t.startswith("```"):
            lines = t.splitlines()
            if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
                t = "\n".join(lines[1:-1]).strip()
        return t