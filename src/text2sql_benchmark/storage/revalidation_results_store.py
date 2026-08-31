"""Persistencia da Etapa 3 — revalidacao das queries geradas pelo text2sql.

A Etapa 2 mede o efeito dos indices sobre as queries gabarito do BIRD. Esta
etapa mede o efeito sobre as queries que o modelo realmente gerou na Etapa 1,
que e a pergunta pratica: os indices sugeridos ajudam a carga que o text2sql
produz, ou foram desenhados para uma carga que nao e a que roda?
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .index_results_store import QueryPerformance


@dataclass
class RevalidationQueryResult:
    instance_id: int
    db_id: str
    difficulty: str
    sql_generated: str
    # Vem da Etapa 1: permite separar o ganho de performance entre queries
    # corretas e incorretas na analise.
    execution_accuracy: bool
    before: QueryPerformance   # banco sem os indices
    after: QueryPerformance    # banco com os indices da Etapa 2
    improved: bool
    new_index_used: bool


@dataclass
class RevalidationResult:
    db_id: str
    model: str
    dialect: str
    # Rastreabilidade: de quais rodadas vieram as queries e os indices.
    source_stage1_run: str
    source_stage2_run: str
    indexes_applied: int = 0
    indexes_failed: int = 0
    query_results: list[dict] = field(default_factory=list)
    total_queries: int = 0
    queries_measured: int = 0
    queries_skipped: int = 0
    queries_improved: int = 0
    queries_using_new_index: int = 0
    avg_latency_before_ms: float = 0.0
    avg_latency_after_ms: float = 0.0
    # Razao das medias: sensivel a outliers, util para tempo total de carga.
    speedup_ratio: float = 1.0
    # Mediana dos speedups por query: o numero robusto para reportar.
    median_speedup: float = 1.0
    error: str | None = None


def resumir(query_results: list[RevalidationQueryResult]) -> dict:
    """Calcula os agregados de uma lista de medicoes."""
    if not query_results:
        return {}
    antes = [q.before.latency_ms for q in query_results]
    depois = [q.after.latency_ms for q in query_results]
    media_antes = statistics.mean(antes)
    media_depois = statistics.mean(depois)
    por_query = [
        (q.before.latency_ms / q.after.latency_ms)
        for q in query_results
        if q.after.latency_ms > 0
    ]
    return {
        "queries_measured": len(query_results),
        "queries_improved": sum(1 for q in query_results if q.improved),
        "queries_using_new_index": sum(1 for q in query_results if q.new_index_used),
        "avg_latency_before_ms": media_antes,
        "avg_latency_after_ms": media_depois,
        "speedup_ratio": media_antes / media_depois if media_depois > 0 else 1.0,
        "median_speedup": statistics.median(por_query) if por_query else 1.0,
    }


class RevalidationResultsStore:
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._results: list[RevalidationResult] = []
        self._run_id: str | None = None

    def begin(self, run_id: str) -> None:
        """Liga a persistencia incremental: cada add() grava o arquivo."""
        self._run_id = run_id

    def add(self, result: RevalidationResult) -> None:
        self._results.append(result)
        if self._run_id:
            self.save(self._run_id)

    def save(self, run_id: str) -> Path:
        path = self._output_dir / f"{run_id}.json"
        payload = json.dumps(
            [asdict(r) for r in self._results], indent=2, ensure_ascii=False
        )
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
        return path

    def load(self, path: Path) -> list[RevalidationResult]:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._results = [RevalidationResult(**d) for d in data]
        return self._results
