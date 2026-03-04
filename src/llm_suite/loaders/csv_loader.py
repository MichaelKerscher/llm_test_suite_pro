import csv
import json
from pathlib import Path
from typing import Any, Dict, List
from llm_suite.models import TestCase

def _safe_json_loads(s: str) -> Any:
    if s is None:
        return {}
    s = str(s).strip()
    if not s:
        return {}
    return json.loads(s)

def load_csv(path: str) -> List[TestCase]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Testfile not found: {p}")

    out: List[TestCase] = []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            tc_id = (row.get("testcase_id") or "").strip()
            if not tc_id:
                raise ValueError(f"Row {i}: testcase_id missing")

            user_msg = (row.get("user_message") or "").strip()
            if not user_msg:
                raise ValueError(f"Row {i} ({tc_id}): user_message missing")

            ctx = _safe_json_loads(row.get("context_json", ""))

            out.append(TestCase(
                testcase_id=tc_id,
                incident_id=(row.get("incident_id") or "").strip() or "UNKNOWN",
                context_level=(row.get("context_level") or "").strip(),
                strategy=(row.get("strategy") or "").strip().upper() or "UNKNOWN",
                user_message=user_msg,
                context_json=ctx if isinstance(ctx, dict) else {"_value": ctx},
            ))
    return out