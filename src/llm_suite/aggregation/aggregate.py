import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Any


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
    return out


def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if isinstance(x, (int, float))]
    return (sum(xs) / len(xs)) if xs else None


def _safe_get_score(run: dict, key: str) -> float | None:
    """
    Extract score from run['judge']['scores'][key] if present.
    """
    j = run.get("judge")
    if not isinstance(j, dict):
        return None
    scores = j.get("scores")
    if not isinstance(scores, dict):
        return None
    v = scores.get(key)
    return float(v) if isinstance(v, (int, float)) else None


def _overall_from_scores(run: dict) -> float | None:
    # prefer logged overall_score if present
    ov = run.get("overall_score")
    if isinstance(ov, (int, float)):
        return float(ov)

    vals = [_safe_get_score(run, k) for k in ["R", "H", "S", "D", "K"]]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return (sum(vals) / len(vals)) if vals else None


def _summary(rows: list[dict]) -> dict:
    runtimes = [r.get("runtime_s") for r in rows]
    overall = [_overall_from_scores(r) for r in rows]
    R = [_safe_get_score(r, "R") for r in rows]
    H = [_safe_get_score(r, "H") for r in rows]
    S = [_safe_get_score(r, "S") for r in rows]
    D = [_safe_get_score(r, "D") for r in rows]
    K = [_safe_get_score(r, "K") for r in rows]

    has_judge = [1 if isinstance(r.get("judge"), dict) else 0 for r in rows]

    return {
        "n": len(rows),
        "mean_runtime_s": _mean([x for x in runtimes if isinstance(x, (int, float))]),
        "judge_rate": _mean(has_judge),
        "mean_R": _mean([x for x in R if isinstance(x, (int, float))]),
        "mean_H": _mean([x for x in H if isinstance(x, (int, float))]),
        "mean_S": _mean([x for x in S if isinstance(x, (int, float))]),
        "mean_D": _mean([x for x in D if isinstance(x, (int, float))]),
        "mean_K": _mean([x for x in K if isinstance(x, (int, float))]),
        "mean_overall": _mean([x for x in overall if isinstance(x, (int, float))]),
    }


def _strategy_of(r: dict) -> str:
    s = (r.get("strategy") or "").strip().upper()
    return s or "UNKNOWN"


def _context_level_of(r: dict) -> str:
    cl = (r.get("context_level") or "").strip()
    return cl or "unknown"


def _incident_of(r: dict) -> str:
    inc = (r.get("incident_id") or "").strip()
    return inc or "UNKNOWN"


def _delta(a: dict | None, b: dict | None) -> dict | None:
    """
    Compute b-a for overall and each rubric score.
    Returns None if one side missing.
    """
    if not a or not b:
        return None

    def dv(key: str) -> float | None:
        va = _safe_get_score(a, key)
        vb = _safe_get_score(b, key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            return float(vb) - float(va)
        return None

    ova = _overall_from_scores(a)
    ovb = _overall_from_scores(b)
    d_overall = (ovb - ova) if (isinstance(ova, (int, float)) and isinstance(ovb, (int, float))) else None

    return {
        "d_overall": d_overall,
        "dR": dv("R"),
        "dH": dv("H"),
        "dS": dv("S"),
        "dD": dv("D"),
        "dK": dv("K"),
    }


def write_aggregate(run_dir: str):
    base = Path(run_dir)
    results_path = base / "results.jsonl"
    errors_path = base / "errors.jsonl"

    results = _read_jsonl(results_path)
    errors = _read_jsonl(errors_path)

    # Basic run health
    n_results = len(results)
    n_errors = len(errors)

    # "Ok" results = those with an answer (even if judge missing)
    ok_rows = [r for r in results if isinstance(r.get("answer"), str) and r.get("answer") != ""]
    n_ok = len(ok_rows)

    # Judge rows = those with judge dict
    judged_rows = [r for r in results if isinstance(r.get("judge"), dict)]
    n_judged = len(judged_rows)

    # Success rate is relative to intended attempts:
    # If you log a result only when generation succeeded, then total attempted ~= n_ok + n_errors
    n_attempted = n_ok + n_errors
    success_rate = (n_ok / n_attempted) if n_attempted else None

    # Summaries
    summary_overall = _summary(results)

    by_strategy = defaultdict(list)
    by_context = defaultdict(list)
    for r in results:
        by_strategy[_strategy_of(r)].append(r)
        by_context[_context_level_of(r)].append(r)

    summary_by_strategy = {k: _summary(v) for k, v in sorted(by_strategy.items())}
    summary_by_context = {k: _summary(v) for k, v in sorted(by_context.items())}

    # Deltas per incident (uses strategy labels S0/S1/S2)
    by_inc = defaultdict(list)
    for r in results:
        by_inc[_incident_of(r)].append(r)

    deltas = []
    for inc, rows in sorted(by_inc.items()):
        # pick best representative per strategy (if duplicates, prefer those with judge)
        pick = {}
        for r in rows:
            s = _strategy_of(r)
            if s not in ("S0", "S1", "S2"):
                continue
            if s not in pick:
                pick[s] = r
            else:
                # prefer judged row
                if not isinstance(pick[s].get("judge"), dict) and isinstance(r.get("judge"), dict):
                    pick[s] = r

        s0, s1, s2 = pick.get("S0"), pick.get("S1"), pick.get("S2")

        row = {"incident_id": inc}
        d_s1_s0 = _delta(s0, s1)
        d_s2_s1 = _delta(s1, s2)
        d_s2_s0 = _delta(s0, s2)

        if d_s1_s0:
            row["S1_minus_S0"] = d_s1_s0
        if d_s2_s1:
            row["S2_minus_S1"] = d_s2_s1
        if d_s2_s0:
            row["S2_minus_S0"] = d_s2_s0

        if len(row.keys()) > 1:
            deltas.append(row)

    # Error analysis (optional)
    err_types = Counter()
    dns_count = 0
    for e in errors:
        et = (e.get("exception_type") or "").strip() or "Unknown"
        err_types[et] += 1
        if e.get("is_dns_error") is True:
            dns_count += 1

    aggregate = {
        "n_results": n_results,
        "n_ok": n_ok,
        "n_errors": n_errors,
        "n_attempted": n_attempted,
        "success_rate": success_rate,
        "n_judged": n_judged,
        "judge_rate_overall": (n_judged / n_results) if n_results else None,
        "summary_overall": summary_overall,
        "by_strategy": summary_by_strategy,
        "by_context_level": summary_by_context,
        "deltas_by_incident": deltas,
        "errors_summary": {
            "n_errors": n_errors,
            "dns_errors": dns_count,
            "top_exception_types": err_types.most_common(10),
        },
    }

    (base / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")

    # Short Markdown report for humans
    md = []
    md.append(f"# Aggregation Report\n\n")
    md.append(f"- results: **{n_results}**\n")
    md.append(f"- attempted (ok+errors): **{n_attempted}**\n")
    md.append(f"- ok: **{n_ok}**\n")
    md.append(f"- errors: **{n_errors}**\n")
    md.append(f"- success_rate: **{success_rate:.2%}**\n" if isinstance(success_rate, (int, float)) else "- success_rate: **n/a**\n")
    md.append(f"- judge_rate (of results): **{(n_judged/n_results):.2%}**\n" if n_results else "- judge_rate: **n/a**\n")

    md.append("\n## Means by strategy\n")
    for strat, s in summary_by_strategy.items():
        md.append(f"### {strat} (n={s['n']})\n")
        md.append(f"- mean runtime: {s['mean_runtime_s']}\n")
        md.append(f"- mean R/H/S/D/K: {s['mean_R']}/{s['mean_H']}/{s['mean_S']}/{s['mean_D']}/{s['mean_K']}\n")
        md.append(f"- mean overall: {s['mean_overall']}\n")

    md.append("\n## Means by context level\n")
    for cl, s in summary_by_context.items():
        md.append(f"### {cl} (n={s['n']})\n")
        md.append(f"- mean runtime: {s['mean_runtime_s']}\n")
        md.append(f"- mean R/H/S/D/K: {s['mean_R']}/{s['mean_H']}/{s['mean_S']}/{s['mean_D']}/{s['mean_K']}\n")
        md.append(f"- mean overall: {s['mean_overall']}\n")

    md.append("\n## Incidents with deltas\n")
    md.append(f"- incidents_with_any_deltas: **{len(deltas)}**\n")

    if n_errors:
        md.append("\n## Errors (top)\n")
        for et, c in err_types.most_common(10):
            md.append(f"- {et}: {c}\n")
        md.append(f"\n- dns_errors: **{dns_count}**\n")

    (base / "report.md").write_text("".join(md), encoding="utf-8")