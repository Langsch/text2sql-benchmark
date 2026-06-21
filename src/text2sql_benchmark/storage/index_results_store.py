from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class IndexApplication:
    statement: str
    success: bool
    error: str | None = None


@dataclass
class QueryPerformance:
    latency_ms: float
    explain_raw: str
    uses_index: bool
    scan_type: str


@dataclass
class QueryResult:
    instance_id: int
    sql: str
    difficulty: str
    before: QueryPerformance
    after: QueryPerformance
    improved: bool
    new_index_used: bool


@dataclass
class IndexBenchmarkResult:
    db_id: str
    model: str
    # LLM interaction
    index_prompt_tokens: int
    index_output_tokens: int
    index_llm_latency_ms: float
    raw_llm_response: str
    # Indexes suggested
    indexes_suggested: list[dict] = field(default_factory=list)
    indexes_applied: int = 0
    indexes_failed: int = 0
    # Per-query before/after
    query_results: list[dict] = field(default_factory=list)
    # Aggregate stats
    total_queries: int = 0
    queries_improved: int = 0
    queries_using_new_index: int = 0
    avg_latency_before_ms: float = 0.0
    avg_latency_after_ms: float = 0.0
    speedup_ratio: float = 1.0
    error: str | None = None


class IndexResultsStore:
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._results: list[IndexBenchmarkResult] = []

    def add(self, result: IndexBenchmarkResult) -> None:
        self._results.append(result)

    def save(self, run_id: str) -> Path:
        path = self._output_dir / f"{run_id}.json"
        path.write_text(
            json.dumps([asdict(r) for r in self._results], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def load(self, path: Path) -> list[IndexBenchmarkResult]:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._results = [IndexBenchmarkResult(**d) for d in data]
        return self._results
