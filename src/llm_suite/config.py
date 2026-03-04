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

    # 506-specific (optional, used by provider_506)
    org_id: str
    data_collection_id: str
    generator_assistant_id: str
    judge_assistant_id: str
    internal_system_prompt: bool
    default_mode: str


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


# -------------------------
# small env helpers
# -------------------------
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


# -------------------------
# Provider config builder
# -------------------------
def _provider_cfg(prefix: str) -> ProviderCfg:
    """
    Build provider config from generic PREFIX_* keys,
    with robust fallbacks for CompanyGPT/506.ai env naming.
    """

    # Provider name
    provider = _env_str(f"{prefix}_PROVIDER", "dummy")

    # Model: prefer PREFIX_MODEL, fallback to TESTSUITE_DEFAULT_MODEL (legacy)
    model = _env_str(f"{prefix}_MODEL", "")
    if not model:
        model = _env_str("TESTSUITE_DEFAULT_MODEL", "dummy-model")

    # Base URL: prefer PREFIX_BASE_URL, fallback to COMPANYGPT_BASE_URL
    base_url = _env_str(f"{prefix}_BASE_URL", "")
    if not base_url:
        base_url = _env_str("COMPANYGPT_BASE_URL", "")

    # API Key: prefer PREFIX_API_KEY, fallback to COMPANYGPT_API_KEY
    api_key = _env_str(f"{prefix}_API_KEY", "")
    if not api_key:
        api_key = _env_str("COMPANYGPT_API_KEY", "")

    timeout_s = _env_int(f"{prefix}_TIMEOUT_S", 60)
    temperature = _env_float(f"{prefix}_TEMPERATURE", 0.2)

    extra_headers_json = _env_str(f"{prefix}_EXTRA_HEADERS_JSON", "{}")
    extra_body_json = _env_str(f"{prefix}_EXTRA_BODY_JSON", "{}")
    endpoint_path = _env_str(f"{prefix}_ENDPOINT_PATH", "")

    # 506 keys (kept provider-agnostic but available)
    org_id = _env_str("COMPANYGPT_ORG_ID", "")
    data_collection_id = _env_str("COMPANYGPT_DATA_COLLECTION_ID", "")
    generator_assistant_id = _env_str("COMPANYGPT_GENERATOR_ASSISTANT_ID", "")
    judge_assistant_id = _env_str("COMPANYGPT_JUDGE_ASSISTANT_ID", "")
    internal_system_prompt = _env_bool("COMPANYGPT_INTERNAL_SYSTEM_PROMPT", True)
    default_mode = _env_str("COMPANYGPT_DEFAULT_MODE", "BASIC")

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
    )


def load_config(args) -> ResolvedConfig:
    load_dotenv()

    run_mode = _env_str("TESTSUITE_RUN_MODE", "incident").lower()
    if args.mode:
        run_mode = str(args.mode).strip().lower()

    enable_judge = (not args.no_judge) and _env_bool("JUDGE_ENABLE", True)

    runs_dir = _env_str("RUNS_DIR", "runs")
    run_name = _env_str("RUN_NAME", "local-dev")

    llm = _provider_cfg("LLM")

    # Build judge cfg but inherit LLM values if judge-specific vars are absent/blank
    judge = _provider_cfg("JUDGE")

    # Inherit *only if not explicitly set*
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
    )


def make_run_id(cfg: ResolvedConfig) -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # keep it filesystem-friendly
    provider = (cfg.llm.provider or "unknown").replace("/", "_").replace(" ", "_")
    run_name = (cfg.run_name or "run").replace("/", "_").replace(" ", "_")
    return f"{ts}__{run_name}__{provider}"