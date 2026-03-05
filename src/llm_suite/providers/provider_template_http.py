import json
import random
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from llm_suite.config import ProviderCfg
from llm_suite.providers.base import Provider, LLMRequest, LLMResponse


# -----------------------------
# Error type with rich context
# -----------------------------
class ProviderCallError(RuntimeError):
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


# -----------------------------
# Helpers
# -----------------------------
def _host_from_base_url(base_url: str) -> str:
    try:
        u = urlparse(base_url)
        return u.hostname or base_url
    except Exception:
        return base_url


def _is_dns_error(exc: BaseException) -> bool:
    # Windows common: 11001/11002
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
    if _is_dns_error(exc):
        return True
    if isinstance(exc, OSError):
        return True
    return False


def _append_context_to_prompt(prompt: str, context: dict | None) -> str:
    if not context:
        return prompt
    try:
        ctx_str = json.dumps(context, ensure_ascii=False, sort_keys=True, indent=2)
    except Exception:
        ctx_str = str(context)
    return prompt + "\n\n[CONTEXT_JSON]\n<<<\n" + ctx_str + "\n>>>\n"


# -----------------------------
# Template Provider
# -----------------------------
class ProviderTemplateHTTP(Provider):
    """
    Generic HTTP provider template.

    You should:
      1) rename class + file to provider_<vendor>.py
      2) set `name = "provider_<vendor>"`
      3) implement:
         - _build_headers()
         - _build_payload_generate()
         - _parse_text()
      4) set correct endpoint paths in env or hardcode defaults
    """

    name = "provider_template_http"

    def __init__(self, cfg: ProviderCfg):
        self.cfg = cfg

        if not self.cfg.base_url:
            raise ValueError("LLM_BASE_URL is required for HTTP provider template.")
        self.base = self.cfg.base_url.rstrip("/")
        self.host = _host_from_base_url(self.base)

        # Retry knobs (passed from config)
        self.max_retries = int(getattr(cfg, "max_retries", 3) or 3)
        self.backoff_base_s = float(getattr(cfg, "retry_backoff_base_s", 1.0) or 1.0)
        self.backoff_max_s = float(getattr(cfg, "retry_backoff_max_s", 8.0) or 8.0)
        self.jitter_s = float(getattr(cfg, "retry_jitter_s", 0.25) or 0.25)

        self._client = httpx.Client(timeout=httpx.Timeout(self.cfg.timeout_s))

        # If vendor needs a specific endpoint, set via env:
        # LLM_ENDPOINT_PATH=/v1/chat/completions  (example)
        self.endpoint_path = (self.cfg.endpoint_path or "").strip() or "/v1/chat/completions"

    # ---------- customize ----------
    def _build_headers(self) -> dict:
        """
        Customize per vendor.
        Default: Bearer auth if api_key set; plus JSON content-type.
        Also merges extra headers JSON if provided.
        """
        headers = {"Content-Type": "application/json"}

        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"

        # Optional: merge LLM_EXTRA_HEADERS_JSON
        try:
            extra = json.loads(self.cfg.extra_headers_json or "{}")
            if isinstance(extra, dict):
                headers.update({str(k): str(v) for k, v in extra.items()})
        except Exception:
            pass

        return headers

    def _build_payload_generate(self, req: LLMRequest) -> dict:
        """
        Customize per vendor.
        Default assumes OpenAI-ish schema: model + messages.
        """
        prompt = _append_context_to_prompt(req.prompt, req.context)

        payload = {
            "model": req.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": req.temperature,
        }

        # Optional: merge LLM_EXTRA_BODY_JSON
        try:
            extra_body = json.loads(self.cfg.extra_body_json or "{}")
            if isinstance(extra_body, dict):
                payload.update(extra_body)
        except Exception:
            pass

        return payload

    def _parse_text(self, vendor_json: dict) -> str:
        """
        Customize per vendor response shape.
        Default: OpenAI-ish choices[0].message.content.
        """
        try:
            return (vendor_json["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            return json.dumps(vendor_json, ensure_ascii=False)[:2000]

    # ---------- retry wrapper ----------
    def _sleep_backoff(self, attempt_1based: int):
        base = min(self.backoff_max_s, self.backoff_base_s * (2 ** (attempt_1based - 1)))
        jitter = random.uniform(0, self.jitter_s)
        time.sleep(base + jitter)

    def _post_with_retry(self, *, phase: str, url: str, headers: dict, payload: dict) -> dict:
        last_exc: BaseException | None = None

        for attempt in range(0, self.max_retries + 1):
            try:
                r = self._client.post(url, headers=headers, json=payload)

                # Retryable HTTP
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

                # Non-retry HTTP errors
                if r.status_code >= 400:
                    raise ProviderCallError(
                        phase=phase,
                        provider=self.name,
                        host=self.host,
                        message=f"HTTP {r.status_code}",
                        exception_type="httpx.HTTPStatusError",
                        is_dns_error=False,
                        is_network_error=False,
                        retries=attempt,
                        status_code=r.status_code,
                        response_text=r.text[:500] if r.text else None,
                    )

                return r.json()

            except ProviderCallError:
                # already enriched
                raise

            except Exception as e:
                last_exc = e
                is_dns = _is_dns_error(e)
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
            is_dns_error=_is_dns_error(last_exc) if last_exc else False,
            is_network_error=True,
            retries=self.max_retries,
        )

    # ---------- Provider API ----------
    def generate(self, req: LLMRequest) -> LLMResponse:
        url = f"{self.base}{self.endpoint_path}"
        headers = self._build_headers()
        payload = self._build_payload_generate(req)

        data = self._post_with_retry(phase="generate", url=url, headers=headers, payload=payload)
        text = self._parse_text(data)
        return LLMResponse(text=text, raw={"provider": self.name})

    def judge(self, prompt: str, model: str, temperature: float = 0.0) -> str:
        """
        Optional. If you want separate judge behavior, override build_payload/parse_text
        or map to the same endpoint.
        """
        url = f"{self.base}{self.endpoint_path}"
        headers = self._build_headers()

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }

        data = self._post_with_retry(phase="judge", url=url, headers=headers, payload=payload)
        return self._parse_text(data)