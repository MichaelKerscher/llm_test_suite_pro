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


def run_pipeline(cfg: ResolvedConfig):
    run_id = make_run_id(cfg)
    run_dir = os.path.join(cfg.runs_dir, run_id)
    logger = RunLogger(run_dir)

    # manifest snapshot
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
        }
    )

    # load testcases
    tcs = load_csv(cfg.tests_path)

    # providers
    llm = make_provider(cfg.llm)
    judge = make_provider(cfg.judge) if cfg.enable_judge else None

    # execution
    if cfg.run_mode == "testcase":
        for tc in tcs:
            _run_one(tc, llm, judge, cfg, logger)
        write_aggregate(run_dir)
        return

    # incident mode
    groups = _group_by_incident(tcs)
    for incident_id in sorted(groups.keys()):
        group = _stable_sort(groups[incident_id])
        _run_incident_group(incident_id, group, llm, judge, cfg, logger)

    write_aggregate(run_dir)


def _run_one(tc: TestCase, llm, judge, cfg: ResolvedConfig, logger: RunLogger):
    """
    testcase-mode: generate + single-mode judge
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
                expected_elements="",  # TODO: later from CSV/rules
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
    except Exception as e:
        rt = round(time.perf_counter() - t0, 3)
        logger.log_error(
            {
                "testcase_id": tc.testcase_id,
                "incident_id": tc.incident_id,
                "error": str(e),
                "runtime_s": rt,
            }
        )


def _run_incident_group(
    incident_id: str,
    group: list[TestCase],
    llm,
    judge,
    cfg: ResolvedConfig,
    logger: RunLogger,
):
    """
    incident-mode:
      - generate answers for all testcases in the incident
      - judge once with INCIDENT-MODE prompt (JSON array)
      - attach each judge block back to each testcase result
    """
    generated: list[dict] = []

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
            logger.log_error(
                {
                    "testcase_id": tc.testcase_id,
                    "incident_id": tc.incident_id,
                    "error": str(e),
                    "runtime_s": rt,
                }
            )

    # 2) judge once per incident
    judge_arr = None
    if judge and generated:
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


def __mk_req(tc: TestCase, model: str, temperature: float):
    from llm_suite.providers.base import LLMRequest

    return LLMRequest(
        model=model,
        prompt=tc.user_message,
        context=tc.context_json,
        temperature=temperature,
        input_type="text",
    )