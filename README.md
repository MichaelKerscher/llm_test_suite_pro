# llm_test_suite_pro

Generalisierte LLM-Test-Suite für die Masterarbeit (und den Unternehmenseinsatz):  
Ziel ist eine **Provider-agnostische** Testpipeline, die sich per **`.env`** auf unterschiedliche LLM-Aufrufstellen konfigurieren lässt (externe Dienstleister / CompanyGPTs, Azure OpenAI, Self-hosted Modelle).

## Ziele (Kurz)
- **Einfacher Betrieb im Unternehmen**: nur `.env` befüllen, Tests laufen lassen
- **Austauschbare Provider** (Beispiel zuerst: `506.ai`, später: `Azure OpenAI`, optional: self-hosted/OpenAI-kompatibel)
- **Reproduzierbarkeit**: Run-ID, Manifest, JSONL-Logging
- **Standard-Pipeline** (Default):
  **Loader → LLM-Call → Judge → Logging → Aggregation (nach Run-Ende)**
- **Strategy Hook optional** via CLI (Default: aus)

---

## Projektstatus
Dieses Repository wird **schrittweise** aufgebaut:
1) Repo/README/Grundstruktur ✅  
2) Minimaler “smoke test” ohne echten Provider (Dummy-Provider)  
3) Provider-Integration: **506.ai** (externer Dienstleister)  
4) Erweiterung: **Azure OpenAI** (weiterer Dienstleister)  
5) Optional: OpenAI-kompatible Self-hosted Provider

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

## .env Konfiguration (Konzept)

### Default LLM Provider
Die Suite wird über folgende, möglichst generische Variablen konfiguriert:
- `LLM_PROVIDER` - Provider-Name (z.B. `provider_506`, später `azure_openai`)
- `LLM_BASE` - Basis-URL des Dienstleisters
- `LLM_API_KEY` - Token/Key
- `LLM-MODEL` - Modellname / Modell-Auswahl
- `LLM_TIMEOUT_S`, `LLM_TEMPERATURE`
- Optional:
  - `LLM_EXTRA_HEADERS_JSON`
  - `LLM_EXTRA_BODY_JSON`

### Judge Provider (optional)
Der Judge ist konzeptionell ein zweiter Provider (kann identisch oder getrennt sein):
- `JUDGE_ENABLE=true|false`
- `JUDGE_PROVIDER`, `JUDGE_BASE_URL`, `JUDGE_API_KEY`, `JUDGE_MODEL`, `JUDGE_TIMEOUT_S`

---

## CLI (geplant)
Beispiele:  
```bash
# Default: Strategy Hook OFF
python scripts/run_suite.py --tests data/examples/testcases_minimal.csv

# Strategy Hook ON
python scripts/run_suite.py --tests data/examples/testcases_minimal.csv --enable-strategy-hook

# Strategy Hook ON + erzwinge Strategy
python scripts/run_suite.py --tests data/examples/testcases_minimal.csv --enable-strategy-hook --strategy S2
```

---

## Testdatenformat (Start: CSV)
Zum Start wird CSV unterstützt (später optional JSON).  
  
Minimalbeispiel: `data/examples/testcases_minimal.csv`
```csv
id,question,expected_keywords
t001,"Wie resette ich eine Straßenlampe nach einem Ausfall?","reset;controller;power-cycle"
t002,"Ich habe Spotty Connectivity. Was soll ich dokumentieren?","offline;sync;notes"
```

---

## Output / Runs (geplant)
Jeder Run schreibt in `runs/<run_id>/`:  
- `manifest.json` - Snapshot der Run-Konfiguration (env+cli resolved, Versionen, etc.)
- `results.jsonl` - eine Zeile pro Testfall (Provider, Prompt-Hash, Response, Judge-Score, Runtime)
- `errors.jsonl` - optionale Fehler pro Testfall
- `aggregate.json` - Aggregation nach Run-Ende (Means, Counts, etc.)
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