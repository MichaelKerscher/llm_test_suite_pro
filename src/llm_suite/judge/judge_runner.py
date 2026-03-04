import json

def _strip_code_fences(s: str) -> str:
    if not isinstance(s, str):
        return s
    t = s.strip()
    if not t.startswith("```"):
        return t
    lines = t.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return t

def parse_judge_obj(raw: str) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(_strip_code_fences(raw))
    except Exception:
        return None

def parse_judge_array(raw: str) -> list[dict] | None:
    if not raw:
        return None
    try:
        obj = json.loads(_strip_code_fences(raw))
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