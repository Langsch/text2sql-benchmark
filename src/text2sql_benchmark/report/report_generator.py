from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..storage import BenchmarkResult, ResultsStore

console = Console()


class ReportGenerator:
    def __init__(self, results: list[BenchmarkResult]) -> None:
        self._results = results

    @classmethod
    def from_file(cls, path: Path) -> "ReportGenerator":
        store = ResultsStore(path.parent)
        return cls(store.load(path))

    def summary_table(self) -> None:
        """Exibe tabela resumo: modelo × SGBD → EX, EM médios."""
        from collections import defaultdict

        grouped: dict[tuple[str, str], list[BenchmarkResult]] = defaultdict(list)
        for r in self._results:
            grouped[(r.model, r.sgbd)].append(r)

        table = Table(title="Benchmark Summary")
        table.add_column("Model")
        table.add_column("SGBD")
        table.add_column("N")
        table.add_column("EX %", justify="right")
        table.add_column("EM %", justify="right")
        table.add_column("Avg Latency (ms)", justify="right")

        for (model, sgbd), results in sorted(grouped.items()):
            n = len(results)
            ex_pct = sum(r.execution_accuracy for r in results) / n * 100
            em_pct = sum(r.exact_match for r in results) / n * 100
            avg_lat = sum(r.latency_ms for r in results) / n
            table.add_row(model, sgbd, str(n), f"{ex_pct:.1f}", f"{em_pct:.1f}", f"{avg_lat:.1f}")

        console.print(table)

    def export_csv(self, output_path: Path) -> None:
        # TODO: exportar resultados em CSV para análise estatística no TCC
        raise NotImplementedError
