import json
import random
import socket
import time
from urllib.parse import urlparse

import httpx

from llm_suite.config import ProviderCfg
from llm_suite.providers.base import Provider, LLMRequest, LLMResponse


def _append_context_to_prompt(prompt: str, context: dict | None) -> str:
    if not context:
        return prompt
    ctx_str = json.dumps(context, ensure_ascii=False, sort_keys=True, indent=2)
    return prompt + "\n\n[CONTEXT_JSON]\n<<<\n" + ctx_str + "\n>>>\n"


def _host_from_base_url(base_url: str) -> str:
    try:
        u = urlparse(base_url)
        return u.hostname or base_url
    except Exception:
        return base_url


def _is_dns_oserror(exc: BaseException) -> bool:
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in (11001, 11002):
        return True
    if isinstance(exc, socket.gaierror) and getattr(exc, "errno", None) in (11001, 11002):
        return True
    return False


def _is_transient_network_error(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout)):
        return True
    if isinstance(exc, httpx.NetworkError):
        return True
    if _is_dns_oserror(exc):
        return True
    if isinstance(exc, OSError):
        return True
    return False


class ProviderCallError(RuntimeError):
    """
    Raised by provider calls with rich context so pipeline can log properly.
    """

    def __init__(
        self,
        *,
        phase: str,
        provider: str,
        host: str,
        message: str,
        exception_type: str,
        is_dns_error: bool,
        is_network_error: bool,
        retries: int,
        status_code: int | None = None,
        response_text: str | None = None,
    ):
        super().__init__(message)
        self.phase = phase
        self.provider = provider
        self.host = host
        self.exception_type = exception_type
        self.is_dns_error = is_dns_error
        self.is_network_error = is_network_error
        self.retries = retries
        self.status_code = status_code
        self.response_text = response_text


class Provider506(Provider):
    name = "provider_506"

    def __init__(self, cfg: ProviderCfg):
        self.cfg = cfg

        if not self.cfg.base_url:
            raise ValueError("LLM_BASE_URL (or COMPANYGPT_BASE_URL fallback) is required for provider_506.")
        if not self.cfg.org_id:
            raise ValueError("COMPANYGPT_ORG_ID is required for provider_506.")
        if not self.cfg.api_key:
            raise ValueError("LLM_API_KEY (or COMPANYGPT_API_KEY fallback) is required for provider_506.")

        self.base = self.cfg.base_url.rstrip("/")
        self.host = _host_from_base_url(self.base)

        self.headers_auth = {
            "api-organization-id": self.cfg.org_id,
            "api-key": self.cfg.api_key,
        }
        self.headers_json = {
            **self.headers_auth,
            "Content-Type": "application/json",
        }

        self._client = httpx.Client(timeout=httpx.Timeout(self.cfg.timeout_s))
        self.max_retries = int(getattr(cfg, "max_retries", 3) or 3)
        self.backoff_base_s = float(getattr(cfg, "retry_backoff_base_s", 1.0) or 1.0)
        self.backoff_max_s = float(getattr(cfg, "retry_backoff_max_s", 8.0) or 8.0)
        self.jitter_s = float(getattr(cfg, "retry_jitter_s", 0.25) or 0.25)

    def _sleep_backoff(self, attempt: int):
        base = min(self.backoff_max_s, self.backoff_base_s * (2 ** (attempt - 1)))
        jitter = random.uniform(0, self.jitter_s)
        time.sleep(base + jitter)

    def _post_json_with_retry(self, *, phase: str, url: str, params: dict, payload: dict) -> dict:
        last_exc: BaseException | None = None

        for attempt in range(0, self.max_retries + 1):
            try:
                r = self._client.post(url, headers=self.headers_json, params=params, json=payload)

                if r.status_code in (429, 502, 503, 504):
                    if attempt < self.max_retries:
                        self._sleep_backoff(attempt + 1)
                        continue
                    raise ProviderCallError(
                        phase=phase,
                        provider=self.name,
                        host=self.host,
                        message=f"HTTP {r.status_code} after retries",
                        exception_type="httpx.HTTPStatusError",
                        is_dns_error=False,
                        is_network_error=True,
                        retries=attempt,
                        status_code=r.status_code,
                        response_text=r.text[:500] if r.text else None,
                    )

                r.raise_for_status()
                return r.json()

            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response else None
                text = None
                try:
                    text = e.response.text[:500] if e.response and e.response.text else None
                except Exception:
                    pass

                raise ProviderCallError(
                    phase=phase,
                    provider=self.name,
                    host=self.host,
                    message=str(e),
                    exception_type=type(e).__name__,
                    is_dns_error=False,
                    is_network_error=False,
                    retries=attempt,
                    status_code=status,
                    response_text=text,
                ) from e

            except Exception as e:
                last_exc = e
                is_dns = _is_dns_oserror(e)
                is_net = _is_transient_network_error(e)

                if is_net and attempt < self.max_retries:
                    self._sleep_backoff(attempt + 1)
                    continue

                raise ProviderCallError(
                    phase=phase,
                    provider=self.name,
                    host=self.host,
                    message=str(e),
                    exception_type=type(e).__name__,
                    is_dns_error=is_dns,
                    is_network_error=is_net,
                    retries=attempt,
                ) from e

        raise ProviderCallError(
            phase=phase,
            provider=self.name,
            host=self.host,
            message=str(last_exc) if last_exc else "Unknown error",
            exception_type=type(last_exc).__name__ if last_exc else "Unknown",
            is_dns_error=_is_dns_oserror(last_exc) if last_exc else False,
            is_network_error=True,
            retries=self.max_retries,
        )

    def _chat_no_stream(
        self,
        *,
        phase: str,
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

        data = self._post_json_with_retry(phase=phase, url=url, params=params, payload=payload)
        return (data.get("content") or "").strip()

    def generate(self, req: LLMRequest) -> LLMResponse:
        prompt = _append_context_to_prompt(req.prompt, req.context)
        txt = self._chat_no_stream(
            phase="generate",
            model_id=req.model,
            prompt=prompt,
            temperature=req.temperature,
            selected_mode=self.cfg.default_mode,
            assistant_id=self.cfg.generator_assistant_id or None,
            internal_system_prompt=self.cfg.internal_system_prompt,
        )
        return LLMResponse(text=txt, raw={"provider": self.name})

    def judge(self, prompt: str, model: str, temperature: float = 0.0) -> str:
        txt = self._chat_no_stream(
            phase="judge",
            model_id=model,
            prompt=prompt,
            temperature=temperature,
            selected_mode=self.cfg.default_mode,
            assistant_id=self.cfg.judge_assistant_id or None,
            internal_system_prompt=False,
        )
        t = txt.strip()
        if t.startswith("```"):
            lines = t.splitlines()
            if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
                t = "\n".join(lines[1:-1]).strip()
        return t