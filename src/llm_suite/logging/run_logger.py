import json
from pathlib import Path
from typing import Any, Dict

class RunLogger:
    def __init__(self, run_dir: str):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.results_path = self.run_dir / "results.jsonl"
        self.errors_path = self.run_dir / "errors.jsonl"

    def write_manifest(self, manifest: Dict[str, Any]):
        (self.run_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def log_result(self, obj: Dict[str, Any]):
        with self.results_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def log_error(self, obj: Dict[str, Any]):
        with self.errors_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")