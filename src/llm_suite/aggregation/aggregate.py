import json
from pathlib import Path
from collections import defaultdict

def aggregate_run(run_dir: str) -> dict:
    p = Path(run_dir) / "results.jsonl"
    rows = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))

    by_context = defaultdict(list)
    for r in rows:
        by_context[r.get("context_level", "unknown")].append(r)

    def mean(xs):
        xs = [x for x in xs if isinstance(x, (int, float))]
        return sum(xs)/len(xs) if xs else None

    summary = {"n": len(rows), "by_context_level": {}}
    for cl, rs in sorted(by_context.items()):
        summary["by_context_level"][cl] = {
            "n": len(rs),
            "mean_runtime_s": mean([x.get("runtime_s") for x in rs]),
            "mean_overall": mean([x.get("overall_score") for x in rs]),
        }
    return summary

def write_aggregate(run_dir: str):
    out = aggregate_run(run_dir)
    Path(run_dir, "aggregate.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")