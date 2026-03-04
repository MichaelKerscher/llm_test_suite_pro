import json
import os
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

@dataclass
class ResolvedConfig:
    tests_path: str
    run_mode: str
    enable_judge: bool
    enable_strategy_hook: bool
    forced_strategy: str | None

    # provider
    llm_provider: str
    judge_provider: str
    runs_dir: str
    run_name: str

def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

def load_config(args) -> ResolvedConfig:
    load_dotenv()

    run_mode = (args.mode or os.getenv("TESTSUITE_RUN_MODE", "incident")).strip().lower()
    enable_judge = (not args.no_judge) and _env_bool("JUDGE_ENABLE", True)

    runs_dir = os.getenv("RUNS_DIR", "runs").strip()
    run_name = os.getenv("RUN_NAME", "local-dev").strip()

    llm_provider = os.getenv("LLM_PROVIDER", "dummy").strip()
    judge_provider = os.getenv("JUDGE_PROVIDER", llm_provider).strip()

    return ResolvedConfig(
        tests_path=args.tests,
        run_mode=run_mode,
        enable_judge=enable_judge,
        enable_strategy_hook=bool(args.enable_strategy_hook),
        forced_strategy=(args.strategy.strip().upper() if args.strategy else None),
        llm_provider=llm_provider,
        judge_provider=judge_provider,
        runs_dir=runs_dir,
        run_name=run_name,
    )

def make_run_id(cfg: ResolvedConfig) -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{ts}__{cfg.run_name}__{cfg.llm_provider}"