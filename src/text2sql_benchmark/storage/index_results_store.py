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
    # Prompt exato enviado ao modelo — necessario para reproduzir a rodada.
    index_prompt: str = ""
    # Dialeto usado para montar o prompt (sqlite | postgresql | mariadb).
    dialect: str = "sqlite"
    # True quando o provedor cortou a resposta em max_tokens: a lista de
    # indices esta incompleta e o numero sugerido nao reflete o modelo.
    truncated: bool = False
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
        self._run_id: str | None = None

    def begin(self, run_id: str) -> None:
        """Liga a persistencia incremental: cada add() passa a gravar o arquivo.

        Sem isso os resultados ficam so em memoria ate o fim da rodada, e uma
        queda na ultima combinacao perde a rodada inteira.
        """
        self._run_id = run_id

    def add(self, result: IndexBenchmarkResult) -> None:
        self._results.append(result)
        if self._run_id:
            self.save(self._run_id)

    def save(self, run_id: str) -> Path:
        path = self._output_dir / f"{run_id}.json"
        payload = json.dumps(
            [asdict(r) for r in self._results], indent=2, ensure_ascii=False
        )
        # Grava num temporario e renomeia: rename e atomico no mesmo filesystem,
        # entao uma queda no meio da escrita nao deixa JSON truncado no lugar.
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
        return path

    def load(self, path: Path) -> list[IndexBenchmarkResult]:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._results = [IndexBenchmarkResult(**d) for d in data]
        return self._results
