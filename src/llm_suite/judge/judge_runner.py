import json
from llm_suite.judge.rubric import default_score_block

def parse_judge_array(raw: str) -> list[dict] | None:
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, list) else None
    except Exception:
        return None

def pick_block_for_test(test_id: str, arr: list[dict] | None) -> dict | None:
    if not arr:
        return None
    for b in arr:
        if isinstance(b, dict) and str(b.get("test_id", "")).strip() == test_id:
            return b
    return None