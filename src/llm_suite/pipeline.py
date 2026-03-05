import os
import time
from collections import defaultdict

from llm_suite.config import ResolvedConfig, make_run_id
from llm_suite.loaders.csv_loader import load_csv
from llm_suite.providers.registry import make_provider
from llm_suite.logging.run_logger import RunLogger
from llm_suite.aggregation.aggregate import write_aggregate
from llm_suite.models import TestCase

from llm_suite.judge.judge_prompts import (
    build_judge_prompt_single,
    build_judge_prompt_incident,
)
from llm_suite.judge.judge_runner import (
    parse_judge_obj,
    parse_judge_array,
    pick_block_for_test,
)

try:
    from llm_suite.providers.provider_506 import ProviderCallError
except Exception:
    ProviderCallError = None


def _group_by_incident(tcs: list[TestCase]) -> dict[str, list[TestCase]]:
    g: dict[str, list[TestCase]] = defaultdict(list)
    for tc in tcs:
        g[tc.incident_id].append(tc)
    return g


def _stable_sort(group: list[TestCase]) -> list[TestCase]:
    return sorted(group, key=lambda x: x.testcase_id)


def _mean_overall_from_judge_block(jb: dict | None) -> float | None:
    if not jb or not isinstance(jb, dict):
        return None
    scores = jb.get("scores")
    if not isinstance(scores, dict):
        return None
    vals = [scores.get(k) for k in ["R", "H", "S", "D", "K"]]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return (sum(vals) / len(vals)) if vals else None


def _mk_error_payload(
    *,
    testcase_id: str,
    incident_id: str,
    phase: str,
    provider: str,
    host: str | None,
    exc: Exception,
    runtime_s: float,
):
    is_dns_error = False
    is_network_error = False
    retries = 0
    status_code = None
    response_text = None
    exception_type = type(exc).__name__
    msg = str(exc)

    if ProviderCallError is not None and isinstance(exc, ProviderCallError):
        is_dns_error = bool(getattr(exc, "is_dns_error", False))
        is_network_error = bool(getattr(exc, "is_network_error", False))
        retries = int(getattr(exc, "retries", 0) or 0)
        status_code = getattr(exc, "status_code", None)
        response_text = getattr(exc, "response_text", None)
        exception_type = getattr(exc, "exception_type", exception_type)
        msg = str(exc)

    return {
        "testcase_id": testcase_id,
        "incident_id": incident_id,
        "phase": phase,
        "provider": provider,
        "host": host,
        "exception_type": exception_type,
        "error": msg,
        "is_dns_error": is_dns_error,
        "is_network_error": is_network_error,
        "retries": retries,
        "status_code": status_code,
        "response_text": response_text,
        "runtime_s": runtime_s,
    }


def run_pipeline(cfg: ResolvedConfig):
    run_id = make_run_id(cfg)
    run_dir = os.path.join(cfg.runs_dir, run_id)
    logger = RunLogger(run_dir)

    logger.write_manifest(
        {
            "run_id": run_id,
            "tests_path": cfg.tests_path,
            "run_mode": cfg.run_mode,
            "enable_judge": cfg.enable_judge,
            "enable_strategy_hook": cfg.enable_strategy_hook,
            "forced_strategy": cfg.forced_strategy,
            "llm_provider": cfg.llm.provider,
            "judge_provider": cfg.judge.provider,
            "llm_model": cfg.llm.model,
            "judge_model": cfg.judge.model if cfg.enable_judge else None,
            "max_retries": cfg.max_retries,
            "fail_fast": cfg.fail_fast,
            "fail_fast_threshold": cfg.fail_fast_threshold,
        }
    )

    tcs = load_csv(cfg.tests_path)
    llm = make_provider(cfg.llm)
    judge = make_provider(cfg.judge) if cfg.enable_judge else None

    if cfg.run_mode == "testcase":
        consecutive_net_errors = 0
        for tc in tcs:
            ok, was_net = _run_one(tc, llm, judge, cfg, logger)
            if not ok and was_net:
                consecutive_net_errors += 1
            elif ok:
                consecutive_net_errors = 0

            if cfg.fail_fast and consecutive_net_errors >= cfg.fail_fast_threshold:
                raise SystemExit(
                    f"[FAIL-FAST] Aborting after {consecutive_net_errors} consecutive network errors."
                )

        write_aggregate(run_dir)
        return

    groups = _group_by_incident(tcs)

    consecutive_net_errors = 0
    for incident_id in sorted(groups.keys()):
        group = _stable_sort(groups[incident_id])

        ok, net_errors_in_incident = _run_incident_group(incident_id, group, llm, judge, cfg, logger)

        # if whole incident had network errors, count them as consecutive signal
        if net_errors_in_incident > 0 and not ok:
            consecutive_net_errors += net_errors_in_incident
        else:
            consecutive_net_errors = 0

        if cfg.fail_fast and consecutive_net_errors >= cfg.fail_fast_threshold:
            raise SystemExit(
                f"[FAIL-FAST] Aborting after {consecutive_net_errors} consecutive network errors."
            )

    write_aggregate(run_dir)


def _run_one(tc: TestCase, llm, judge, cfg: ResolvedConfig, logger: RunLogger) -> tuple[bool, bool]:
    """
    Returns (ok, was_network_error)
    """
    t0 = time.perf_counter()
    try:
        ans = llm.generate(req=__mk_req(tc, model=cfg.llm.model, temperature=cfg.llm.temperature)).text
        rt = round(time.perf_counter() - t0, 3)

        judge_block = None
        if judge:
            jp = build_judge_prompt_single(
                testcase_id=tc.testcase_id,
                user_message=tc.user_message,
                context_json=tc.context_json,
                assistant_answer=ans,
                expected_elements="",
                asset_type="streetlight",
                fault_type="unknown",
            )
            raw = judge.judge(prompt=jp, model=cfg.judge.model, temperature=cfg.judge.temperature)
            judge_block = parse_judge_obj(raw)

        overall = _mean_overall_from_judge_block(judge_block)

        logger.log_result(
            {
                "testcase_id": tc.testcase_id,
                "incident_id": tc.incident_id,
                "context_level": tc.context_level,
                "strategy": tc.strategy,
                "user_message": tc.user_message,
                "context_json": tc.context_json,
                "answer": ans,
                "runtime_s": rt,
                "judge": judge_block,
                "overall_score": overall,
            }
        )
        return True, False

    except Exception as e:
        rt = round(time.perf_counter() - t0, 3)

        payload = _mk_error_payload(
            testcase_id=tc.testcase_id,
            incident_id=tc.incident_id,
            phase=getattr(e, "phase", "generate_or_judge"),
            provider=getattr(e, "provider", cfg.llm.provider),
            host=getattr(e, "host", None),
            exc=e,
            runtime_s=rt,
        )
        logger.log_error(payload)
        return False, bool(payload.get("is_network_error", False))


def _run_incident_group(
    incident_id: str,
    group: list[TestCase],
    llm,
    judge,
    cfg: ResolvedConfig,
    logger: RunLogger,
) -> tuple[bool, int]:
    """
    Returns (ok, network_error_count_in_incident)
    """
    generated: list[dict] = []
    net_errs = 0

    # 1) generate all answers
    for tc in group:
        t0 = time.perf_counter()
        try:
            ans = llm.generate(req=__mk_req(tc, model=cfg.llm.model, temperature=cfg.llm.temperature)).text
            rt = round(time.perf_counter() - t0, 3)

            generated.append(
                {
                    "test_id": tc.testcase_id,
                    "incident_id": tc.incident_id,
                    "context_level": tc.context_level,
                    "strategy": tc.strategy,
                    "user_message": tc.user_message,
                    "context_json": tc.context_json,
                    "answer": ans,
                    "runtime_s": rt,
                }
            )
        except Exception as e:
            rt = round(time.perf_counter() - t0, 3)
            payload = _mk_error_payload(
                testcase_id=tc.testcase_id,
                incident_id=tc.incident_id,
                phase=getattr(e, "phase", "generate"),
                provider=getattr(e, "provider", cfg.llm.provider),
                host=getattr(e, "host", None),
                exc=e,
                runtime_s=rt,
            )
            if payload.get("is_network_error"):
                net_errs += 1
            logger.log_error(payload)

    # 2) judge once per incident
    judge_arr = None
    if judge and generated:
        t0 = time.perf_counter()
        try:
            jp = build_judge_prompt_incident(
                incident_id=incident_id,
                blocks=[
                    {
                        "test_id": r["test_id"],
                        "context_level": r["context_level"],
                        "user_message": r["user_message"],
                        "context_json": r["context_json"],
                        "answer": r["answer"],
                    }
                    for r in generated
                ],
                expected_elements="",
                asset_type="streetlight",
                fault_type="unknown",
            )
            raw = judge.judge(prompt=jp, model=cfg.judge.model, temperature=cfg.judge.temperature)
            judge_arr = parse_judge_array(raw)
        except Exception as e:
            rt = round(time.perf_counter() - t0, 3)
            payload = _mk_error_payload(
                testcase_id="__INCIDENT_JUDGE__",
                incident_id=incident_id,
                phase=getattr(e, "phase", "judge"),
                provider=getattr(e, "provider", cfg.judge.provider),
                host=getattr(e, "host", None),
                exc=e,
                runtime_s=rt,
            )
            if payload.get("is_network_error"):
                net_errs += 1
            logger.log_error(payload)
            judge_arr = None

    # 3) attach judge blocks and log per testcase
    for r in generated:
        jb = pick_block_for_test(r["test_id"], judge_arr) if judge_arr else None
        overall = _mean_overall_from_judge_block(jb)

        logger.log_result(
            {
                "testcase_id": r["test_id"],
                "incident_id": r["incident_id"],
                "context_level": r["context_level"],
                "strategy": r["strategy"],
                "user_message": r["user_message"],
                "context_json": r["context_json"],
                "answer": r["answer"],
                "runtime_s": r["runtime_s"],
                "judge": jb,
                "overall_score": overall,
            }
        )

    ok = (net_errs == 0)
    return ok, net_errs


def __mk_req(tc: TestCase, model: str, temperature: float):
    from llm_suite.providers.base import LLMRequest

    return LLMRequest(
        model=model,
        prompt=tc.user_message,
        context=tc.context_json,
        temperature=temperature,
        input_type="text",
    )