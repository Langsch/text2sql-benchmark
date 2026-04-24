from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class BenchmarkResult:
    instance_id: int
    db_id: str
    difficulty: str
    model: str
    sgbd: str
    sql_generated: str
    sql_gold: str
    execution_accuracy: bool
    exact_match: bool
    latency_ms: float
    explain_raw: str
    explain_parsed: dict
    error: str | None = None


class ResultsStore:
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._results: list[BenchmarkResult] = []

    def add(self, result: BenchmarkResult) -> None:
        self._results.append(result)

    def save(self, run_id: str) -> Path:
        path = self._output_dir / f"{run_id}.json"
        path.write_text(
            json.dumps([asdict(r) for r in self._results], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def load(self, path: Path) -> list[BenchmarkResult]:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._results = [BenchmarkResult(**d) for d in data]
        return self._results
