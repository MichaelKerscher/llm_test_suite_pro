import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Any


# -----------------------------
# IO helpers
# -----------------------------
def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


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


def _write_json(path: Path, obj: Any):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# -----------------------------
# Stats helpers
# -----------------------------
def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if isinstance(x, (int, float))]
    return (sum(xs) / len(xs)) if xs else None


def _strategy_of(r: dict) -> str:
    s = (r.get("strategy") or "").strip().upper()
    return s or "UNKNOWN"


def _incident_of(r: dict) -> str:
    inc = (r.get("incident_id") or "").strip()
    return inc or "UNKNOWN"


def _safe_get_score(run: dict, key: str) -> float | None:
    j = run.get("judge")
    if not isinstance(j, dict):
        return None
    scores = j.get("scores")
    if not isinstance(scores, dict):
        return None
    v = scores.get(key)
    return float(v) if isinstance(v, (int, float)) else None


def _overall_from_scores(run: dict) -> float | None:
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


def _delta(a: dict | None, b: dict | None) -> dict | None:
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


# -----------------------------
# Snapshot aggregation
# -----------------------------
def _compute_snapshot(run_dir: Path) -> dict:
    results_path = run_dir / "results.jsonl"
    errors_path = run_dir / "errors.jsonl"
    manifest_path = run_dir / "manifest.json"

    results = _read_jsonl(results_path)
    errors = _read_jsonl(errors_path)
    manifest = _read_json(manifest_path) or {}

    n_results = len(results)
    n_errors = len(errors)

    ok_rows = [r for r in results if isinstance(r.get("answer"), str) and r.get("answer") != ""]
    n_ok = len(ok_rows)

    n_attempted = n_ok + n_errors
    success_rate = (n_ok / n_attempted) if n_attempted else None

    judged_rows = [r for r in results if isinstance(r.get("judge"), dict)]
    n_judged = len(judged_rows)

    by_strategy = defaultdict(list)
    for r in results:
        by_strategy[_strategy_of(r)].append(r)

    summary_by_strategy = {k: _summary(v) for k, v in sorted(by_strategy.items())}
    summary_overall = _summary(results)

    by_inc = defaultdict(list)
    for r in results:
        by_inc[_incident_of(r)].append(r)

    deltas = []
    for inc, rows in sorted(by_inc.items()):
        pick = {}
        for r in rows:
            s = _strategy_of(r)
            if s not in ("S0", "S1", "S2"):
                continue
            if s not in pick:
                pick[s] = r
            else:
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

    err_types = Counter()
    dns_count = 0
    by_phase = Counter()
    by_provider = Counter()
    for e in errors:
        err_types[(e.get("exception_type") or "Unknown")] += 1
        if e.get("is_dns_error") is True:
            dns_count += 1
        by_phase[(e.get("phase") or "unknown")] += 1
        by_provider[(e.get("provider") or "unknown")] += 1

    snapshot = {
        "run_id": manifest.get("run_id") or run_dir.name,
        "manifest": manifest,
        "n_results": n_results,
        "n_ok": n_ok,
        "n_errors": n_errors,
        "n_attempted": n_attempted,
        "success_rate": success_rate,
        "n_judged": n_judged,
        "judge_rate_overall": (n_judged / n_results) if n_results else None,
        "summary_overall": summary_overall,
        "by_strategy": summary_by_strategy,
        "deltas_by_incident": deltas,
        "errors_summary": {
            "n_errors": n_errors,
            "dns_errors": dns_count,
            "top_exception_types": err_types.most_common(10),
            "by_phase": by_phase.most_common(),
            "by_provider": by_provider.most_common(),
        },
    }
    return snapshot


def _write_report_md(run_dir: Path, snap: dict):
    md = []
    md.append("# Aggregation Report\n\n")
    md.append(f"- run_id: **{snap.get('run_id')}**\n")
    md.append(f"- attempted: **{snap.get('n_attempted')}**\n")
    md.append(f"- ok: **{snap.get('n_ok')}**\n")
    md.append(f"- errors: **{snap.get('n_errors')}**\n")

    sr = snap.get("success_rate")
    md.append(f"- success_rate: **{sr:.2%}**\n" if isinstance(sr, (int, float)) else "- success_rate: **n/a**\n")

    jr = snap.get("judge_rate_overall")
    md.append(f"- judge_rate: **{jr:.2%}**\n" if isinstance(jr, (int, float)) else "- judge_rate: **n/a**\n")

    md.append("\n## Means by strategy\n")
    for strat, s in (snap.get("by_strategy") or {}).items():
        md.append(f"### {strat} (n={s.get('n')})\n")
        md.append(f"- mean runtime: {s.get('mean_runtime_s')}\n")
        md.append(
            f"- mean R/H/S/D/K: {s.get('mean_R')}/{s.get('mean_H')}/{s.get('mean_S')}/{s.get('mean_D')}/{s.get('mean_K')}\n"
        )
        md.append(f"- mean overall: {s.get('mean_overall')}\n")

    md.append("\n## Incidents with deltas\n")
    md.append(f"- incidents_with_any_deltas: **{len(snap.get('deltas_by_incident') or [])}**\n")

    es = snap.get("errors_summary") or {}
    if (es.get("n_errors") or 0) > 0:
        md.append("\n## Errors (top)\n")
        for et, c in (es.get("top_exception_types") or [])[:10]:
            md.append(f"- {et}: {c}\n")
        md.append(f"\n- dns_errors: **{es.get('dns_errors')}**\n")

    (run_dir / "report.md").write_text("".join(md), encoding="utf-8")


# -----------------------------
# History aggregation across runs
# -----------------------------
def _list_run_dirs(runs_root: Path) -> list[Path]:
    if not runs_root.exists():
        return []
    return sorted([p for p in runs_root.iterdir() if p.is_dir()], key=lambda p: p.name)


def _extract_run_ts(run_id: str) -> str:
    return run_id.split("__")[0] if "__" in run_id else run_id


def _history_by_run(snapshots: list[dict]) -> dict:
    out = {}
    for s in snapshots:
        run_id = s.get("run_id")
        if not run_id:
            continue
        per_strategy = s.get("by_strategy") or {}

        out[run_id] = {
            "ts": _extract_run_ts(run_id),
            "success_rate": s.get("success_rate"),
            "n_attempted": s.get("n_attempted"),
            "n_errors": s.get("n_errors"),
            "per_strategy": per_strategy,
        }
    return out


def _history_overall(history_by_run: dict) -> dict:
    strat_metric_values = defaultdict(lambda: defaultdict(list))

    for _, run_obj in history_by_run.items():
        per_strategy = run_obj.get("per_strategy") or {}
        for strat, summ in per_strategy.items():
            for metric in ["mean_R", "mean_H", "mean_S", "mean_D", "mean_K", "mean_overall", "mean_runtime_s"]:
                v = summ.get(metric)
                if isinstance(v, (int, float)):
                    strat_metric_values[strat][metric].append(float(v))

    def stats(xs: list[float]) -> dict:
        return {
            "n_runs": len(xs),
            "mean_of_run_means": _mean(xs),
            "min_run_mean": min(xs) if xs else None,
            "max_run_mean": max(xs) if xs else None,
        }

    overall = {"per_strategy": {}}
    for strat in sorted(strat_metric_values.keys()):
        m = strat_metric_values[strat]
        overall["per_strategy"][strat] = {metric: stats(vals) for metric, vals in m.items()}

    return overall


def _fmt_delta(cur: float | None, prev: float | None) -> str:
    if not isinstance(cur, (int, float)) or not isinstance(prev, (int, float)):
        return ""
    d = float(cur) - float(prev)
    sign = "+" if d >= 0 else ""
    return f" ({sign}{d:.2f})"


def _write_history_report_md(run_dir: Path, history_by_run: dict, *, last_n: int = 5):
    # sort runs by timestamp prefix (run_id begins with yyyy-mm-dd_hh-mm-ss)
    run_ids = sorted(history_by_run.keys())
    if not run_ids:
        (run_dir / "history_report.md").write_text("# History Report\n\nNo runs found.\n", encoding="utf-8")
        return

    tail = run_ids[-last_n:]

    md = []
    md.append("# History Report\n\n")
    md.append(f"Showing last **{len(tail)}** runs (of {len(run_ids)} total).\n\n")

    # Build quick lookup for prev run comparisons
    for i, rid in enumerate(tail):
        cur = history_by_run[rid]
        prev = history_by_run[tail[i - 1]] if i > 0 else None

        md.append(f"## {rid}\n")
        sr = cur.get("success_rate")
        md.append(f"- success_rate: **{sr:.2%}**\n" if isinstance(sr, (int, float)) else "- success_rate: **n/a**\n")
        md.append(f"- attempted: **{cur.get('n_attempted')}**, errors: **{cur.get('n_errors')}**\n")

        md.append("\n### Means by strategy (mean_overall)\n\n")
        md.append("| Strategy | mean_overall | Δ vs prev |\n")
        md.append("|---|---:|---:|\n")

        cur_ps = cur.get("per_strategy") or {}
        prev_ps = (prev.get("per_strategy") or {}) if prev else {}

        # show in stable order
        for strat in ["S0", "S1", "S2", "UNKNOWN"]:
            if strat not in cur_ps:
                continue
            cur_overall = (cur_ps.get(strat) or {}).get("mean_overall")
            prev_overall = (prev_ps.get(strat) or {}).get("mean_overall") if prev else None
            delta_txt = _fmt_delta(cur_overall, prev_overall)
            md.append(f"| {strat} | {cur_overall if cur_overall is not None else 'n/a'} | {delta_txt.strip() or ' '} |\n")

        md.append("\n")

    (run_dir / "history_report.md").write_text("".join(md), encoding="utf-8")


# -----------------------------
# Public entry point
# -----------------------------
def write_aggregate(run_dir: str):
    """
    Writes snapshot for this run, plus history across all runs in RUNS_DIR.
    Outputs (in this run_dir):
      - aggregate.json
      - report.md
      - history_by_run.json
      - history_overall.json
      - history_report.md
    """
    run_path = Path(run_dir)
    snap = _compute_snapshot(run_path)

    _write_json(run_path / "aggregate.json", snap)
    _write_report_md(run_path, snap)

    runs_root = run_path.parent
    run_dirs = _list_run_dirs(runs_root)

    snapshots = []
    for rd in run_dirs:
        agg_path = rd / "aggregate.json"
        if agg_path.exists():
            s = _read_json(agg_path)
            if isinstance(s, dict) and s.get("run_id"):
                snapshots.append(s)
            continue

        res_path = rd / "results.jsonl"
        if res_path.exists():
            try:
                snapshots.append(_compute_snapshot(rd))
            except Exception:
                pass

    hist_by_run = _history_by_run(snapshots)
    hist_overall = _history_overall(hist_by_run)

    _write_json(run_path / "history_by_run.json", hist_by_run)
    _write_json(run_path / "history_overall.json", hist_overall)
    _write_history_report_md(run_path, hist_by_run, last_n=5)