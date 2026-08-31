"""Etapa 3 — os indices da Etapa 2 melhoram as queries geradas na Etapa 1?

A Etapa 2 mede o ganho sobre as queries gabarito do BIRD. Aqui a carga e
outra: as queries que o modelo escreveu. Elas podem fazer JOIN por outra
coluna ou filtrar por outro campo, e nesse caso um indice desenhado sobre o
gabarito simplesmente nao e usado. Descobrir isso e o resultado da etapa.

Nao ha chamada ao LLM: a query e a mesma da Etapa 1, so o banco muda. E isso
que isola o efeito do indice.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import track

from ..config import BenchmarkConfig
from ..db import DBConnector
from ..db.isolation import EstrategiaIsolamento, IsolamentoPorCopia, IsolamentoPorTransacao
from ..metrics import measure_latency
from ..metrics.explain_parsers import (
    MariaDBExplainParser,
    PostgreSQLExplainParser,
    SQLiteExplainParser,
)
from ..storage.index_results_store import QueryPerformance
from ..storage.revalidation_results_store import (
    RevalidationQueryResult,
    RevalidationResult,
    RevalidationResultsStore,
    resumir,
)

console = Console()
_EXPLAIN_PARSERS = {
    "sqlite": SQLiteExplainParser(),
    "postgresql": PostgreSQLExplainParser(),
    "mariadb": MariaDBExplainParser(),
}


# Reaproveita a construcao de conector e as estrategias do runner de indices:
# as duas etapas medem da mesma forma, so muda a carga de queries.
from .index_runner import _abrir_conector, _url_do_dialeto  # noqa: E402


class RevalidationRunner:
    def __init__(self, cfg: BenchmarkConfig, dialect: str = "sqlite") -> None:
        self._cfg = cfg
        self._store = RevalidationResultsStore(cfg.output_dir / "revalidation_runs")
        self._dialect = dialect
        self._explain_parser = _EXPLAIN_PARSERS[dialect]

    def _nova_estrategia(self, conector: DBConnector) -> EstrategiaIsolamento:
        base = self._cfg.output_dir / "revalidation_runs"
        if self._dialect == "sqlite":
            return IsolamentoPorCopia(
                Path(_url_do_dialeto(self._cfg, "sqlite")), base / "tmp_dbs"
            )
        return IsolamentoPorTransacao(
            conector, base / f"indices_pendentes_{self._dialect}.json"
        )

    def run(
        self,
        stage1_path: Path,
        stage2_path: Path,
        model: str,
        db_id: str | None = None,
    ) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{ts}_revalidation_{db_id or 'all'}"
        self._store.begin(run_id)

        stage1 = json.loads(Path(stage1_path).read_text(encoding="utf-8"))
        stage2 = json.loads(Path(stage2_path).read_text(encoding="utf-8"))

        # Queries geradas pelo modelo, agrupadas por banco. Entram apenas as
        # que executaram: uma query que nao roda nao tem latencia a comparar.
        por_banco: dict[str, list[dict]] = defaultdict(list)
        puladas: dict[str, int] = defaultdict(int)
        for r in stage1:
            if r.get("model") != model:
                continue
            if db_id and r["db_id"] != db_id:
                continue
            if r.get("error"):
                puladas[r["db_id"]] += 1
                continue
            por_banco[r["db_id"]].append(r)

        # Indices que a Etapa 2 conseguiu aplicar, por banco.
        indices: dict[str, list[str]] = {}
        for r in stage2:
            if r.get("model") != model or r.get("error"):
                continue
            if db_id and r["db_id"] != db_id:
                continue
            indices[r["db_id"]] = [
                a["statement"] for a in r.get("indexes_suggested", []) if a.get("success")
            ]

        bancos = sorted(set(por_banco) & set(indices))
        faltando = sorted(set(por_banco) - set(indices))
        if faltando:
            console.print(
                f"[yellow]Sem indices na Etapa 2 para: {', '.join(faltando)} "
                "— esses bancos ficam de fora.[/yellow]"
            )

        console.print(
            f"[bold]Run {run_id}[/bold] — {len(bancos)} bancos, "
            f"{sum(len(por_banco[b]) for b in bancos)} queries geradas, "
            f"modelo {model}"
        )

        original = _abrir_conector(self._cfg, self._dialect)
        for banco in track(bancos, description="Revalidacao..."):
            resultado = self._run_single(
                banco, por_banco[banco], indices[banco], original, model,
                puladas.get(banco, 0), Path(stage1_path).name, Path(stage2_path).name,
            )
            self._store.add(resultado)
        original.close()

        path = self._store.save(run_id)
        console.print(f"[green]Resultados salvos em {path}[/green]")
        return path

    def _run_single(
        self,
        db_id: str,
        queries: list[dict],
        statements: list[str],
        original: DBConnector,
        model: str,
        puladas: int,
        origem1: str,
        origem2: str,
    ) -> RevalidationResult:
        console.print(f"  [cyan]{db_id}[/cyan] — {len(queries)} queries, {len(statements)} indices")

        # Baseline ANTES dos indices: no isolamento por transacao eles sao
        # criados no proprio banco, entao medir depois daria baseline indexado.
        antes = [self._medir_uma(original, q["sql_generated"], db_id) for q in queries]

        estrategia = self._nova_estrategia(original)
        indexado, aplicacoes = estrategia.preparar(db_id, statements)
        aplicados = sum(1 for a in aplicacoes if a.success)
        falhos = sum(1 for a in aplicacoes if not a.success)

        medicoes: list[RevalidationQueryResult] = []
        try:
            for q, medida_antes in zip(queries, antes):
                depois = self._medir_uma(indexado, q["sql_generated"], db_id)
                medicoes.append(
                    RevalidationQueryResult(
                        instance_id=q["instance_id"],
                        db_id=db_id,
                        difficulty=q["difficulty"],
                        sql_generated=q["sql_generated"],
                        execution_accuracy=q["execution_accuracy"],
                        before=medida_antes,
                        after=depois,
                        improved=depois.latency_ms < medida_antes.latency_ms,
                        new_index_used=depois.uses_index and not medida_antes.uses_index,
                    )
                )
        finally:
            estrategia.limpar(db_id)

        agg = resumir(medicoes)
        return RevalidationResult(
            db_id=db_id,
            model=model,
            dialect=self._dialect,
            source_stage1_run=origem1,
            source_stage2_run=origem2,
            indexes_applied=aplicados,
            indexes_failed=falhos,
            query_results=[asdict(m) for m in medicoes],
            total_queries=len(queries) + puladas,
            queries_skipped=puladas,
            **agg,
        )

    def _medir_uma(
        self, db: DBConnector, sql: str, db_id: str, runs: int = 3
    ) -> QueryPerformance:
        """Mesmo protocolo da Etapa 2: 1 aquecimento + mediana de 3 execucoes."""
        latencias: list[float] = []
        explain_raw = ""
        usa_indice = False
        scan = "SeqScan"
        timeout = self._cfg.timeout_seconds
        try:
            db.execute(sql, timeout=timeout, db_id=db_id)
            for _ in range(runs):
                with measure_latency() as ms:
                    db.execute(sql, timeout=timeout, db_id=db_id)
                latencias.append(ms[0])
            explain_raw = db.explain(sql, db_id=db_id)
            parsed = self._explain_parser.parse(explain_raw)
            usa_indice = parsed.uses_index
            scan = parsed.scan_type
        except Exception as exc:
            explain_raw = f"ERROR: {exc}"
        return QueryPerformance(
            latency_ms=statistics.median(latencias) if latencias else 0.0,
            explain_raw=explain_raw,
            uses_index=usa_indice,
            scan_type=scan,
        )
