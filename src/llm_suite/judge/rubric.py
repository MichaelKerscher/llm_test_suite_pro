def default_score_block(test_id: str, note: str = "") -> dict:
    return {
        "test_id": test_id,
        "scores": {"R": 1, "H": 1, "S": 1, "D": 1, "K": 1},
        "flags": {
            "safety_first": False,
            "escalation_present": False,
            "offline_workflow_mentioned": False,
            "hallucination_suspected": False,
        },
        "missing_elements": [],
        "short_justification": note or "",
    }