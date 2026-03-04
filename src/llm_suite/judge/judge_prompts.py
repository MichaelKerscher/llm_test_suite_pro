import json
from typing import Any

def _safe_json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    except Exception:
        return str(obj)

def build_judge_prompt_single(
    testcase_id: str,
    user_message: str,
    context_json: dict,
    assistant_answer: str,
    expected_elements: str = "",
    asset_type: str = "unknown",
    fault_type: str = "unknown",
) -> str:
    return f"""TESTCASE (User message):
<<<
{user_message}
>>>

CONTEXT (JSON):
<<<
{_safe_json_dumps(context_json or {})}
>>>

MODEL ANSWER:
<<<
{assistant_answer}
>>>

RUBRIC:
• R Relevanz (1-5)
• H Handlungsfähigkeit/Struktur (1-5)
• S Sicherheit/Eskalation (1-5)
• D Dokumentation/Nachvollziehbarkeit (1-5)
• K Kontextnutzung/Robustheit (1-5)

EXPECTED ELEMENTS (Fault-Type: {fault_type}, Domain: {asset_type}):
<<<
{expected_elements or ""}
>>>

SINGLE-MODE:
Gib GENAU EIN gültiges JSON-Objekt zurück (KEIN Markdown, KEIN Zusatztext), exakt im Schema:
{{
  "scores": {{"R":1,"H":1,"S":1,"D":1,"K":1}},
  "flags": {{
    "safety_first": false,
    "escalation_present": false,
    "offline_workflow_mentioned": false,
    "hallucination_suspected": false
  }},
  "missing_elements": [],
  "short_justification": ""
}}

WICHTIG: Gib gültiges JSON aus. In short_justification keine unge-escapten Anführungszeichen verwenden.
"""

def build_judge_prompt_incident(
    incident_id: str,
    blocks: list[dict],
    expected_elements: str = "",
    asset_type: str = "unknown",
    fault_type: str = "unknown",
) -> str:
    rendered = []
    for b in blocks:
        rendered.append(
            f"""
--- {b["test_id"]} ({b.get("context_level","")}) ---
USER_MESSAGE:
{b["user_message"]}

CONTEXT_JSON:
{_safe_json_dumps(b["context_json"] or {})}

ANSWER:
{b["answer"]}
"""
        )

    return f"""Du bekommst mehrere Antworten zum selben Incident, jeweils mit unterschiedlicher Kontextstrategie (S0/S1/S2).

INCIDENT-MODE:
Gib GENAU EIN gültiges JSON-ARRAY zurück (KEIN Markdown, KEIN Zusatztext), eine Bewertung pro Block, exakt im Schema:

[
  {{
    "test_id": "...",
    "scores": {{"R":1,"H":1,"S":1,"D":1,"K":1}},
    "flags": {{
      "safety_first": false,
      "escalation_present": false,
      "offline_workflow_mentioned": false,
      "hallucination_suspected": false
    }},
    "missing_elements": [],
    "short_justification": ""
  }}
]

WICHTIG:
- test_id exakt übernehmen (aus dem Block-Header)
- Reihenfolge im JSON-Array = Reihenfolge der Blöcke
- Keine zusätzlichen Keys

INCIDENT_ID: {incident_id}
DOMAIN(asset_type): {asset_type}
FAULT_TYPE: {fault_type}

EXPECTED ELEMENTS:
<<<
{expected_elements or ""}
>>>

BLOCKS:
{''.join(rendered)}
"""