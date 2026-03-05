# llm_test_suite_pro

Generalisierte LLM-Test-Suite für die Masterarbeit (und den Unternehmenseinsatz):  
Ziel ist eine **Provider-agnostische** Testpipeline, die sich per **`.env`** auf unterschiedliche LLM-Aufrufstellen konfigurieren lässt (externe Dienstleister / CompanyGPTs, Azure OpenAI, Self-hosted Modelle).

## Ziele (Kurz)
- **Einfacher Betrieb im Unternehmen**: nur `.env` befüllen, Tests laufen lassen
- **Austauschbare Provider** (Beispiel zuerst: `506.ai`, später: `Azure OpenAI`, optional: self-hosted/OpenAI-kompatibel)
- **Reproduzierbarkeit**: Run-ID, Manifest, JSONL-Logging
- **Standard-Pipeline** (Default):
  **Loader -> LLM-Call -> Judge -> Logging -> Aggregation (nach Run-Ende)**
- **Strategy Hook optional** via CLI (Default: aus)

---

## Projektstatus
Dieses Repository wird **schrittweise** aufgebaut:
1) Repo/README/Grundstruktur   
2) Robustheit (Retries / Fail-fast)
3) Aggregation: Snapshot + History
4) Minimaler “smoke test” ohne echten Provider (Dummy-Provider)  
5) Provider-Integration: **506.ai** (externer Dienstleister)
6) Erweiterung: **Azure OpenAI** (weiterer Dienstleister)  
7) Optional: OpenAI-kompatible Self-hosted Provider

---

## Quickstart (lokal)

### Voraussetzungen
- Windows / macOS / Linux
- Python (empfohlen: **3.12**; 3.13 geht meist auch, aber Wheels können bei manchen Paketen fehlen)

### Setup
```bash
py -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

python -m pip install -r requirements.txt
```

### Konfiguration
```bash
copy .env.example .env
# doer: cp .env.example .env
```
Dann .env befüllen (Provider-Keys / Base URL / Modell).  

### Run
```bash
python scripts/run_suite.py --tests data/examples/testcases_minimal.csv
```

---

## .env Konfiguration

### Generisches Provider-Schema (LLM)
Die Suite wird primär über diese generischen Variablen konfiguriert:

- `LLM_PROVIDER` – Provider-Name (z.B. `provider_506`, später `azure_openai`)
- `LLM_BASE_URL` – Basis-URL des Dienstleisters (z.B. `https://companygpt.506.ai:3003`)
- `LLM_API_KEY` – Token/Key (bei 506 optional, falls `COMPANYGPT_API_KEY` gesetzt ist)
- `LLM_MODEL` – Modellname / Modell-ID
- `LLM_TIMEOUT_S`, `LLM_TEMPERATURE`

Optional:
- `LLM_EXTRA_HEADERS_JSON` – zusätzliche Header als JSON (string)
- `LLM_EXTRA_BODY_JSON` – zusätzliche Body-Felder als JSON (string)

### Judge Provider (optional)
Der Judge ist konzeptionell ein zweiter Provider (kann identisch oder getrennt sein):

- `JUDGE_ENABLE=true|false`
- `JUDGE_PROVIDER`, `JUDGE_BASE_URL`, `JUDGE_API_KEY`, `JUDGE_MODEL`, `JUDGE_TIMEOUT_S`, `JUDGE_TEMPERATURE`

**Hinweis (Fallbacks für 506.ai / CompanyGPT):**
Falls `LLM_BASE_URL` / `LLM_API_KEY` nicht gesetzt sind, werden (für `provider_506`) automatisch folgende Variablen als Fallback verwendet:
- `COMPANYGPT_BASE_URL`
- `COMPANYGPT_API_KEY`
Zusätzlich benötigt `provider_506`:
- `COMPANYGPT_ORG_ID`
- optional: `COMPANYGPT_GENERATOR_ASSISTANT_ID`, `COMPANYGPT_JUDGE_ASSISTANT_ID`

---

## CLI

```bash
# Default: incident mode + Judge (wenn JUDGE_ENABLE=true)
python scripts/run_suite.py --tests data/examples/lamp_sample.csv

# ohne Judge
python scripts/run_suite.py --tests data/examples/lamp_sample.csv --no-judge

# Robustheit im Unternehmensnetz (Retries)
python scripts/run_suite.py --tests data/examples/lamp_sample.csv --max-retries 3

# Fail-fast, wenn DNS/Netz dauerhaft weg ist
python scripts/run_suite.py --tests data/examples/lamp_sample.csv --max-retries 2 --fail-fast --fail-fast-threshold 5

# Strategy Hook ON (aktuell nur Vorbereitung)
python scripts/run_suite.py --tests data/examples/lamp_sample.csv --enable-strategy-hook
python scripts/run_suite.py --tests data/examples/lamp_sample.csv --enable-strategy-hook --strategy S2
```

---

## Testdatenformat (CSV)

Start: CSV (später optional JSON).

Pflichtspalten:
- `testcase_id`
- `user_message`
- `context_json` (JSON als String; kann `{}` sein)

Empfohlen (für Incident-Mode / Auswertung):
- `incident_id`
- `strategy` (z.B. `S0`, `S1`, `S2`)

Beispiel:
```csv
testcase_id,incident_id,context_level,strategy,user_message,context_json
INC-LAMP-0001-TC1,INC-LAMP-0001,L0_minimal,S0,"Lampe war vorhin aus, ist jetzt wieder an. (Asset-ID: n571...)","{""asset_osm"":""n571...""}"
INC-LAMP-0001-TC2,INC-LAMP-0001,L2_full,S1,"Lampe war vorhin aus, ist jetzt wieder an.","{""asset"":{...}, ""incident"":{...}}"
```

---

## Output / Runs

Jeder Run schreibt nach `runs/<run_id>/`:

- `manifest.json` – Snapshot der Run-Konfiguration (env + CLI resolved)
- `results.jsonl` – eine Zeile pro Testfall (Antwort, Runtime, optional Judge-Block)
- `errors.jsonl` – Fehlerfälle inkl. Diagnosefeldern (z.B. `phase`, `provider`, `host`, `is_dns_error`, `retries`, `status_code`)
- `aggregate.json` – Snapshot-Aggregation (Counts + Means nach **Strategy S0/S1/S2** + Deltas pro Incident)
- `report.md` – Kurzreport (Snapshot)
- `history_by_run.json` – Zeitreihe über alle Runs (pro Run: Summary nach Strategy)
- `history_overall.json` – Zusammenfassung über alle Runs (mean-of-run-means, min/max)
- `history_report.md` – Kurzreport über die letzten Runs (inkl. Δ vs vorheriger Run)

`runs/` ist in `.gitignore` und wird nicht eingecheckt.

---

## Provider Roadmap

### 1) 506.ai (externer Dienstleister)
- Ziel: Provider-Adapter `provider_506` implementieren
- `.env` soll genügen (Base URL + Key + Model + optional headers/body)

### 2) Azure OpenAI (weiterer Dienstleister)
- `azure_openai` Adapter vorbereiten
- Konfiguration über:
  - `AZURE_OPENAI_ENDPOINT`
  - `AZURE_OPENAI_API_KEY`
  - `AZURE_OPENAI_API_VERSION`
  - `AZURE_OPENAI_DEPLOYMENT`

### 3) Self-hosted / OpenAI-kompatibel (optional)
- Viele lokale/hosted LLMs bieten OpenAI-kompatible Endpoints (`/v1/chat/completions`)
- Adapter `openai_compat` möglich

---

## Entwicklung

### Vorgehen
1. Grundstruktur + Dummy-Provider
2. Logging + Aggregation stabil machen
3. 506.ai Provider ergänzen
4. Azure Provider ergänzen

### Git Workflow (Beispiel)
```bash
git add README.md .env.example requirements.txt .gitignore
git commit -m "Add initial README and project scaffolding"
git push
```

---

## Lizenz / Nutzung

Interne Nutzung für Forschung & Unternehmenseinsatz.  