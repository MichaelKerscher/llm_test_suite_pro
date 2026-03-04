import os
import time
import json
from collections import defaultdict
from llm_suite.config import ResolvedConfig, make_run_id
from llm_suite.loaders.csv_loader import load_csv
from llm_suite.providers.registry import make_provider
from llm_suite.judge.judge_runner import parse_judge_array, pick_block_for_test
from llm_suite.logging.run_logger import RunLogger
from llm_suite.aggregation.aggregate import write_aggregate
from llm_suite.models import TestCase

def _group_by_incident(tcs: list[TestCase]) -> dict[str, list[TestCase]]:
    g = defaultdict(list)
    for tc in tcs:
        g[tc.incident_id].append(tc)
    return g

def _stable_sort(group: list[TestCase]) -> list[TestCase]:
    return sorted(group, key=lambda x: x.testcase_id)

def run_pipeline(cfg: ResolvedConfig):
    run_id = make_run_id(cfg)
    run_dir = os.path.join(cfg.runs_dir, run_id)
    logger = RunLogger(run_dir)

    logger.write_manifest({
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
    })

    tcs = load_csv(cfg.tests_path)

    llm = make_provider(cfg.llm)
    judge = make_provider(cfg.judge) if cfg.enable_judge else None

    if cfg.run_mode == "testcase":
        for tc in tcs:
            _run_one(tc, llm, judge, cfg, logger)
        write_aggregate(run_dir)
        return

    groups = _group_by_incident(tcs)
    for incident_id in sorted(groups.keys()):
        group = _stable_sort(groups[incident_id])
        _run_incident_group(incident_id, group, llm, judge, cfg, logger)

    write_aggregate(run_dir)

def _run_one(tc: TestCase, llm, judge, cfg, logger: RunLogger):
    t0 = time.perf_counter()
    try:
        model = cfg.llm.model
        temp = cfg.llm.temperature
        ans = llm.generate(
            req=__mk_req(tc, model=model, temperature=temp)
        ).text
        rt = round(time.perf_counter() - t0, 3)

        judge_block = None
        overall = None
        if judge:
            raw = judge.judge(prompt=f"Judge: {tc.testcase_id}", model=cfg.judge.model, temperature=cfg.judge.temperature,)
            arr = parse_judge_array(raw)
            judge_block = pick_block_for_test(tc.testcase_id, arr) or None
            if judge_block and isinstance(judge_block.get("scores"), dict):
                sc = judge_block["scores"]
                vals = [sc.get(k) for k in ["R","H","S","D","K"]]
                vals = [v for v in vals if isinstance(v,(int,float))]
                overall = sum(vals)/len(vals) if vals else None

        logger.log_result({
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
        })
    except Exception as e:
        rt = round(time.perf_counter() - t0, 3)
        logger.log_error({
            "testcase_id": tc.testcase_id,
            "incident_id": tc.incident_id,
            "error": str(e),
            "runtime_s": rt,
        })

def _run_incident_group(incident_id: str, group: list[TestCase], llm, judge, cfg, logger):
    # For now: run each testcase individually and optionally attach judge later.
    for tc in group:
        _run_one(tc, llm, judge, cfg, logger)

def __mk_req(tc: TestCase, model: str, temperature: float):
    from llm_suite.providers.base import LLMRequest
    return LLMRequest(
        model=model,
        prompt=tc.user_message,
        context=tc.context_json,
        temperature=temperature,
        input_type="text",
    )