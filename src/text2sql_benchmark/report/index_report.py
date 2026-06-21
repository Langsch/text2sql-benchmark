from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..storage.index_results_store import IndexBenchmarkResult, IndexResultsStore

console = Console()


class IndexReportGenerator:
    def __init__(self, results: list[IndexBenchmarkResult]) -> None:
        self._results = results

    @classmethod
    def from_file(cls, path: Path) -> "IndexReportGenerator":
        store = IndexResultsStore(path.parent)
        return cls(store.load(path))

    def summary_table(self) -> None:
        """Exibe tabela resumo: modelo × db_id → indexes, speedup, queries improved."""
        table = Table(title="Index Benchmark Summary")
        table.add_column("Model")
        table.add_column("Database")
        table.add_column("Indexes Suggested", justify="right")
        table.add_column("Applied", justify="right")
        table.add_column("Failed", justify="right")
        table.add_column("Queries", justify="right")
        table.add_column("Improved", justify="right")
        table.add_column("New Index Used", justify="right")
        table.add_column("Avg Before (ms)", justify="right")
        table.add_column("Avg After (ms)", justify="right")
        table.add_column("Speedup", justify="right")

        for r in sorted(self._results, key=lambda r: (r.model, r.db_id)):
            if r.error:
                table.add_row(
                    r.model, r.db_id,
                    "-", "-", "-", "-", "-", "-", "-", "-",
                    f"[red]ERR[/red]",
                )
                continue
            table.add_row(
                r.model,
                r.db_id,
                str(len(r.indexes_suggested)),
                str(r.indexes_applied),
                str(r.indexes_failed),
                str(r.total_queries),
                str(r.queries_improved),
                str(r.queries_using_new_index),
                f"{r.avg_latency_before_ms:.2f}",
                f"{r.avg_latency_after_ms:.2f}",
                f"{r.speedup_ratio:.2f}x",
            )

        console.print(table)

    def model_summary_table(self) -> None:
        """Exibe tabela agregada por modelo (todos os bancos combinados)."""
        grouped: dict[str, list[IndexBenchmarkResult]] = defaultdict(list)
        for r in self._results:
            if not r.error:
                grouped[r.model].append(r)

        table = Table(title="Index Benchmark - Per Model Summary")
        table.add_column("Model")
        table.add_column("Databases", justify="right")
        table.add_column("Total Indexes", justify="right")
        table.add_column("Total Queries", justify="right")
        table.add_column("Queries Improved %", justify="right")
        table.add_column("Avg Speedup", justify="right")

        for model, results in sorted(grouped.items()):
            n_dbs = len(results)
            total_idx = sum(r.indexes_applied for r in results)
            total_q = sum(r.total_queries for r in results)
            total_improved = sum(r.queries_improved for r in results)
            pct = (total_improved / total_q * 100) if total_q else 0.0
            avg_speedup = (
                sum(r.speedup_ratio for r in results) / n_dbs if n_dbs else 1.0
            )
            table.add_row(
                model,
                str(n_dbs),
                str(total_idx),
                str(total_q),
                f"{pct:.1f}",
                f"{avg_speedup:.2f}x",
            )

        console.print(table)
