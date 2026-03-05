import os
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv


@dataclass
class ProviderCfg:
    provider: str
    model: str
    base_url: str
    api_key: str
    timeout_s: int
    temperature: float

    extra_headers_json: str
    extra_body_json: str
    endpoint_path: str

    # 506-specific
    org_id: str
    data_collection_id: str
    generator_assistant_id: str
    judge_assistant_id: str
    internal_system_prompt: bool
    default_mode: str

    # retry knobs (used by providers)
    max_retries: int
    retry_backoff_base_s: float
    retry_backoff_max_s: float
    retry_jitter_s: float


@dataclass
class ResolvedConfig:
    tests_path: str
    run_mode: str
    enable_judge: bool
    enable_strategy_hook: bool
    forced_strategy: str | None

    runs_dir: str
    run_name: str

    llm: ProviderCfg
    judge: ProviderCfg

    # pipeline knobs
    max_retries: int
    fail_fast: bool
    fail_fast_threshold: int


def _env_str(key: str, default: str = "") -> str:
    v = os.getenv(key)
    return default if v is None else str(v).strip()


def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _env_float(key: str, default: float) -> float:
    v = os.getenv(key)
    if v is None or str(v).strip() == "":
        return default
    try:
        return float(v)
    except Exception:
        return default


def _env_int(key: str, default: int) -> int:
    v = os.getenv(key)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(v)
    except Exception:
        return default


def _provider_cfg(prefix: str, *, max_retries: int) -> ProviderCfg:
    provider = _env_str(f"{prefix}_PROVIDER", "dummy")

    model = _env_str(f"{prefix}_MODEL", "")
    if not model:
        model = _env_str("TESTSUITE_DEFAULT_MODEL", "dummy-model")

    base_url = _env_str(f"{prefix}_BASE_URL", "")
    if not base_url:
        base_url = _env_str("COMPANYGPT_BASE_URL", "")

    api_key = _env_str(f"{prefix}_API_KEY", "")
    if not api_key:
        api_key = _env_str("COMPANYGPT_API_KEY", "")

    timeout_s = _env_int(f"{prefix}_TIMEOUT_S", 60)
    temperature = _env_float(f"{prefix}_TEMPERATURE", 0.2)

    extra_headers_json = _env_str(f"{prefix}_EXTRA_HEADERS_JSON", "{}")
    extra_body_json = _env_str(f"{prefix}_EXTRA_BODY_JSON", "{}")
    endpoint_path = _env_str(f"{prefix}_ENDPOINT_PATH", "")

    org_id = _env_str("COMPANYGPT_ORG_ID", "")
    data_collection_id = _env_str("COMPANYGPT_DATA_COLLECTION_ID", "")
    generator_assistant_id = _env_str("COMPANYGPT_GENERATOR_ASSISTANT_ID", "")
    judge_assistant_id = _env_str("COMPANYGPT_JUDGE_ASSISTANT_ID", "")
    internal_system_prompt = _env_bool("COMPANYGPT_INTERNAL_SYSTEM_PROMPT", True)
    default_mode = _env_str("COMPANYGPT_DEFAULT_MODE", "BASIC")

    # retry knobs (env override possible)
    backoff_base_s = _env_float("RETRY_BACKOFF_BASE_S", 1.0)
    backoff_max_s = _env_float("RETRY_BACKOFF_MAX_S", 8.0)
    jitter_s = _env_float("RETRY_JITTER_S", 0.25)

    return ProviderCfg(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout_s=timeout_s,
        temperature=temperature,
        extra_headers_json=extra_headers_json,
        extra_body_json=extra_body_json,
        endpoint_path=endpoint_path,
        org_id=org_id,
        data_collection_id=data_collection_id,
        generator_assistant_id=generator_assistant_id,
        judge_assistant_id=judge_assistant_id,
        internal_system_prompt=internal_system_prompt,
        default_mode=default_mode,
        max_retries=max_retries,
        retry_backoff_base_s=backoff_base_s,
        retry_backoff_max_s=backoff_max_s,
        retry_jitter_s=jitter_s,
    )


def load_config(args) -> ResolvedConfig:
    load_dotenv()

    run_mode = _env_str("TESTSUITE_RUN_MODE", "incident").lower()
    if args.mode:
        run_mode = str(args.mode).strip().lower()

    enable_judge = (not args.no_judge) and _env_bool("JUDGE_ENABLE", True)

    runs_dir = _env_str("RUNS_DIR", "runs")
    run_name = _env_str("RUN_NAME", "local-dev")

    # pipeline knobs (CLI overrides env)
    max_retries = int(args.max_retries) if getattr(args, "max_retries", None) is not None else _env_int("MAX_RETRIES", 3)
    fail_fast = bool(args.fail_fast) if getattr(args, "fail_fast", None) is not None else _env_bool("FAIL_FAST", False)
    fail_fast_threshold = (
        int(args.fail_fast_threshold)
        if getattr(args, "fail_fast_threshold", None) is not None
        else _env_int("FAIL_FAST_THRESHOLD", 5)
    )

    llm = _provider_cfg("LLM", max_retries=max_retries)

    judge = _provider_cfg("JUDGE", max_retries=max_retries)
    if not _env_str("JUDGE_PROVIDER", ""):
        judge.provider = llm.provider
    if not _env_str("JUDGE_MODEL", ""):
        judge.model = llm.model
    if not _env_str("JUDGE_BASE_URL", ""):
        judge.base_url = llm.base_url
    if not _env_str("JUDGE_API_KEY", ""):
        judge.api_key = llm.api_key
    if not _env_str("JUDGE_TIMEOUT_S", ""):
        judge.timeout_s = llm.timeout_s

    return ResolvedConfig(
        tests_path=args.tests,
        run_mode=run_mode,
        enable_judge=enable_judge,
        enable_strategy_hook=bool(args.enable_strategy_hook),
        forced_strategy=(args.strategy.strip().upper() if args.strategy else None),
        runs_dir=runs_dir,
        run_name=run_name,
        llm=llm,
        judge=judge,
        max_retries=max_retries,
        fail_fast=fail_fast,
        fail_fast_threshold=fail_fast_threshold,
    )


def make_run_id(cfg: ResolvedConfig) -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    provider = (cfg.llm.provider or "unknown").replace("/", "_").replace(" ", "_")
    run_name = (cfg.run_name or "run").replace("/", "_").replace(" ", "_")
    return f"{ts}__{run_name}__{provider}"