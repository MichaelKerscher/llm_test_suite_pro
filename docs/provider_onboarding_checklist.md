# Provider Onboarding Checklist (SOP)

Ziel: Neuer LLM-Dienstleister kann per `.env` als `LLM_PROVIDER=<name>` (und optional `JUDGE_PROVIDER=<name>`) genutzt werden.

---

## Definition of Done
- [ ] `python scripts/run_suite.py --tests data/examples/lamp_sample.csv` läuft durch
- [ ] `runs/<run_id>/aggregate.json` + `history_report.md` werden erzeugt
- [ ] `errors.jsonl` ist diagnostisch (phase/provider/host/is_dns_error/is_network_error/retries/status_code)
- [ ] `.env.example` enthält alle nötigen Keys (ohne Secrets)
- [ ] README kurz ergänzt (Konfiguration + ggf. Einschränkungen)

---

## Phase A — Intake (API verstehen)
- [ ] Interface-Typ: REST / SDK / OpenAI-kompatibel / proprietär
- [ ] Auth: API key header, Bearer, org/tenant header, mTLS?
- [ ] Model-Select: model-id vs deployment-id vs route
- [ ] Limits: RPM/TPM, 429/Retry-After, typische 5xx
- [ ] Minimaler “Hello World” Call (curl/httpie) erfolgreich dokumentiert

Artefakt:
- [ ] Mini-Beispielrequest/-response im internen Wiki oder als Datei in `docs/vendor/<name>/`

---

## Phase B — ENV Contract festlegen
- [ ] Minimale generische Keys: `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- [ ] Zusätzliche Pflichtfelder als vendor-spezifische env keys ODER über JSON:
  - [ ] `LLM_EXTRA_HEADERS_JSON`
  - [ ] `LLM_EXTRA_BODY_JSON`
- [ ] Optional: extra endpoint path (`LLM_ENDPOINT_PATH`) wenn nötig

---

## Phase C — Provider implementieren
- [ ] Neue Datei: `src/llm_suite/providers/provider_<vendor>.py`
- [ ] Implementiert mindestens:
  - [ ] `generate(req) -> LLMResponse(text=...)`
  - [ ] optional `judge(prompt, model, temperature) -> str`
- [ ] Fehlerbehandlung:
  - [ ] Retries für transient: DNS/Connect/Timeout/429/502/503/504
  - [ ] Kein retry für 4xx (Auth/Bad Request)
  - [ ] Wirft ProviderCallError (oder kompatibel), damit Pipeline rich errors loggt
- [ ] Registry: `src/llm_suite/providers/registry.py` kennt Provider-Name

---

## Phase D — Smoke Test (lokal)
- [ ] `.env` befüllt (minimal)
- [ ] Run:
  - [ ] `--max-retries 3` (empfohlen)
  - [ ] optional: `--fail-fast --fail-fast-threshold 5`
- [ ] Artefakte geprüft:
  - [ ] `results.jsonl` enthält Antworten
  - [ ] `errors.jsonl` leer ODER erwartbar
  - [ ] `aggregate.json` enthält `by_strategy` (S0/S1/S2)
  - [ ] `history_report.md` wird erstellt

---

## Phase E — Enterprise-Härtung
- [ ] DNS/Netzwerk-Störung getestet (kurzer Drop) → retries greifen
- [ ] Proxy/VPN/Firewall Anforderungen dokumentiert
- [ ] Rate-limit: 429/Retry-After Verhalten ok

---

## Phase F — Judge-Strategie festlegen
- [ ] Entscheidung: Judge konstant halten vs Provider-Judge
- [ ] Wenn Provider-Judge:
  - [ ] JSON-only Prompt
  - [ ] Parser/Repair robust (falls nötig)

---

## Phase G — Dokumentation & Übergabe
- [ ] `.env.example` erweitert (ohne Secrets)
- [ ] README: Kurzsektion “Provider: <vendor>”
- [ ] Known Issues: Erreichbarkeit, Proxy, Rate-limits, Feature-Scope (text-only, no tools, …)

---

## Phase H — PR Abnahme (1 Minute)
- [ ] Checklist im PR verlinkt
- [ ] Run-ID vom Smoke-Test im PR Text erwähnt
- [ ] Reviewer kann Run reproduzieren