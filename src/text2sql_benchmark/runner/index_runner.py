from __future__ import annotations

import re
import shutil
import statistics
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import track

from ..config import BenchmarkConfig
from ..dataset import BirdLoader, BirdInstance
from ..db import DBConnector, MariaDBConnector, PostgreSQLConnector, SQLiteConnector
from ..db.isolation import (
    EstrategiaIsolamento,
    IsolamentoPorCopia,
    IsolamentoPorTransacao,
)
from ..llm import GroqConnector, LLMConnector
from ..llm.factory import build_llm_connectors
from ..metrics import measure_latency
from ..metrics.explain_parsers import (
    MariaDBExplainParser,
    PostgreSQLExplainParser,
    SQLiteExplainParser,
)
from ..prompt.index_prompt import IndexPromptBuilder
from ..storage.index_results_store import (
    IndexApplication,
    IndexBenchmarkResult,
    IndexResultsStore,
    QueryPerformance,
    QueryResult,
)

console = Console()

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
# A lista de colunas pode conter parenteses aninhados: no MariaDB, indice em
# coluna TEXT exige prefixo — `ON atom(element(10))`. Um `[^)]+` pararia no
# primeiro `)` e truncaria o statement, gerando erro de sintaxe que parece
# culpa do modelo. `(?:[^()]|\([^()]*\))+` casa um nivel de aninhamento.
_CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"[`\"']?\w+[`\"']?\s+ON\s+[`\"']?\w+[`\"']?\s*"
    r"\((?:[^()]|\([^()]*\))+\)\s*;?",
    re.IGNORECASE,
)

_EXPLAIN_PARSERS = {
    "sqlite": SQLiteExplainParser(),
    "postgresql": PostgreSQLExplainParser(),
    "mariadb": MariaDBExplainParser(),
}

# Pausa antes de cada chamada a Groq. Os limites do plano gratuito sao por
# minuto e uma rodada completa dispara 11 chamadas seguidas, o que estoura a
# janela sem esperar. O connector ainda tem retry proprio.
_THROTTLE_SECONDS = 20.0


def _build_run_id(db_id: str | None, difficulty: str | None) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    parts = [ts, "index", db_id or "all"]
    if difficulty:
        parts.append(difficulty)
    return "_".join(parts)


def parse_index_statements(raw: str) -> list[str]:
    """Extract CREATE INDEX statements from raw LLM response text."""
    text = _THINK_RE.sub("", raw).strip()
    fences = _FENCE_RE.findall(text)
    if fences:
        text = "\n".join(fences)
    statements = _CREATE_INDEX_RE.findall(text)
    # Normalize: ensure each ends with a semicolon
    return [s.rstrip(";").strip() + ";" for s in statements]


def _url_do_dialeto(cfg: BenchmarkConfig, dialect: str) -> str:
    for db_cfg in cfg.databases:
        if db_cfg.dialect == dialect and db_cfg.url:
            return db_cfg.url
    raise ValueError(f"Nenhum banco {dialect!r} configurado no .env")


def _abrir_conector(cfg: BenchmarkConfig, dialect: str) -> DBConnector:
    url = _url_do_dialeto(cfg, dialect)
    if dialect == "sqlite":
        return SQLiteConnector(url)
    sqlite_dir = next(
        (d.url for d in cfg.databases if d.dialect == "sqlite"), ""
    )
    if dialect == "postgresql":
        return PostgreSQLConnector(url, sqlite_dir)
    if dialect == "mariadb":
        return MariaDBConnector(url, sqlite_dir)
    raise ValueError(f"Dialeto sem suporte: {dialect!r}")


class IndexBenchmarkRunner:
    def __init__(self, cfg: BenchmarkConfig, dialect: str = "sqlite") -> None:
        self._cfg = cfg
        self._loader = BirdLoader()
        self._prompt_builder = IndexPromptBuilder()
        self._store = IndexResultsStore(cfg.output_dir / "index_runs")
        self._dialect = dialect
        self._explain_parser = _EXPLAIN_PARSERS[dialect]

    def _nova_estrategia(self, conector: DBConnector) -> EstrategiaIsolamento:
        """SQLite isola por copia de arquivo; os servidores, por transacao."""
        base = self._cfg.output_dir / "index_runs"
        if self._dialect == "sqlite":
            return IsolamentoPorCopia(
                Path(_url_do_dialeto(self._cfg, "sqlite")), base / "tmp_dbs"
            )
        return IsolamentoPorTransacao(
            conector, base / f"indices_pendentes_{self._dialect}.json"
        )

    def run(
        self,
        limit: int | None = None,
        difficulty: str | None = None,
        db_id: str | None = None,
        model: str | None = None,
    ) -> Path:
        run_id = _build_run_id(db_id, difficulty)
        self._store.begin(run_id)

        # Load BIRD instances (SQLite only)
        self._loader.load(self._cfg.bird_data_path, dialect="sqlite")
        instances = list(
            self._loader.iter_instances(difficulty=difficulty, limit=limit, db_id=db_id)
        )

        # Group instances by db_id
        by_db: dict[str, list[BirdInstance]] = defaultdict(list)
        for inst in instances:
            by_db[inst.db_id].append(inst)

        # Com `model`, a fabrica filtra por nome e deixa subir o erro de
        # pinagem ausente. Sem a checagem abaixo, um modelo sem chave ou sem
        # pinagem produzia zero combinacoes e gravava um JSON vazio, que so
        # aparece como problema na hora de consolidar.
        llms = build_llm_connectors(self._cfg, model=model)
        if not llms:
            disponiveis = [c.model_name for c in build_llm_connectors(self._cfg)]
            alvo = f"Modelo {model!r} nao tem chave configurada. " if model else ""
            raise ValueError(
                f"{alvo}Modelos prontos para rodar: {disponiveis or '(nenhum)'}"
            )

        total_combos = len(by_db) * len(llms)
        console.print(
            f"[bold]Run {run_id}[/bold] — "
            f"{len(by_db)} databases × {len(llms)} LLMs = {total_combos} combinations, "
            f"{len(instances)} total queries"
        )

        original_db = _abrir_conector(self._cfg, self._dialect)

        combo_items = [
            (current_db_id, llm)
            for current_db_id in sorted(by_db)
            for llm in llms
        ]

        for position, (current_db_id, llm) in enumerate(
            track(combo_items, description="Index benchmark...")
        ):
            # A pausa existe so por causa do teto por minuto do plano gratuito
            # da Groq. Os demais provedores nao precisam esperar.
            if position and isinstance(llm, GroqConnector):
                time.sleep(_THROTTLE_SECONDS)
            db_instances = by_db[current_db_id]
            result = self._run_single(current_db_id, db_instances, llm, original_db)
            self._store.add(result)

        original_db.close()
        path = self._store.save(run_id)
        console.print(f"[green]Resultados salvos em {path}[/green]")
        return path

    def _run_single(
        self,
        db_id: str,
        instances: list[BirdInstance],
        llm: LLMConnector,
        original_db: DBConnector,
    ) -> IndexBenchmarkResult:
        console.print(f"  [cyan]{db_id}[/cyan] × [yellow]{llm.model_name}[/yellow]")

        # --- Step 1: Build prompt and call LLM ---
        schema = original_db.get_schema(db_id)
        gold_queries = [inst.sql_gold for inst in instances]
        prompt = self._prompt_builder.build(
            schema, gold_queries, db_id, dialect=self._dialect
        )

        try:
            llm_response = llm.generate(prompt)
        except Exception as exc:
            console.print(f"    [red]LLM error: {exc}[/red]")
            return IndexBenchmarkResult(
                db_id=db_id,
                model=llm.model_name,
                index_prompt_tokens=0,
                index_output_tokens=0,
                index_llm_latency_ms=0.0,
                raw_llm_response="",
                index_prompt=prompt,
                dialect=self._dialect,
                error=str(exc),
            )

        raw_response = llm_response.sql
        index_statements = parse_index_statements(raw_response)
        console.print(f"    Indexes suggested: {len(index_statements)}")
        if llm_response.truncated:
            console.print(
                "    [red]ATENCAO: resposta truncada em max_tokens — a lista de "
                "indices esta incompleta.[/red]"
            )

        # --- Step 2: Baseline ANTES de qualquer indice ---
        # A ordem importa: no isolamento por transacao (PostgreSQL, MariaDB) os
        # indices sao criados no proprio banco, entao medir o "antes" depois de
        # aplica-los daria um baseline ja indexado. Coletar primeiro vale para
        # as duas estrategias.
        timeout = self._cfg.timeout_seconds
        antes = [
            self._measure_query(original_db, inst.sql_gold, db_id, timeout)
            for inst in instances
        ]

        # --- Step 3: Aplicar os indices conforme a estrategia do dialeto ---
        estrategia = self._nova_estrategia(original_db)
        indexed_db, aplicacoes = estrategia.preparar(db_id, index_statements)
        applications = aplicacoes

        applied = sum(1 for a in aplicacoes if a.success)
        failed = sum(1 for a in aplicacoes if not a.success)
        console.print(f"    Applied: {applied}, Failed: {failed}")

        # --- Step 4: Medir de novo, agora com os indices ---
        query_results: list[QueryResult] = []
        try:
            for inst, medida_antes in zip(instances, antes):
                depois = self._measure_query(
                    indexed_db, inst.sql_gold, db_id, timeout
                )
                query_results.append(
                    QueryResult(
                        instance_id=inst.instance_id,
                        sql=inst.sql_gold,
                        difficulty=inst.difficulty,
                        before=medida_antes,
                        after=depois,
                        improved=depois.latency_ms < medida_antes.latency_ms,
                        new_index_used=depois.uses_index and not medida_antes.uses_index,
                    )
                )
        finally:
            estrategia.limpar(db_id)

        # --- Step 4: Compute aggregate stats ---
        total = len(query_results)
        improved = sum(1 for qr in query_results if qr.improved)
        new_index = sum(1 for qr in query_results if qr.new_index_used)

        before_lats = [qr.before.latency_ms for qr in query_results]
        after_lats = [qr.after.latency_ms for qr in query_results]
        avg_before = statistics.mean(before_lats) if before_lats else 0.0
        avg_after = statistics.mean(after_lats) if after_lats else 0.0
        speedup = avg_before / avg_after if avg_after > 0 else 1.0

        return IndexBenchmarkResult(
            db_id=db_id,
            model=llm.model_name,
            index_prompt_tokens=llm_response.input_tokens,
            index_output_tokens=llm_response.output_tokens,
            index_llm_latency_ms=llm_response.latency_ms,
            raw_llm_response=raw_response,
            index_prompt=prompt,
            dialect=self._dialect,
            truncated=llm_response.truncated,
            provider=llm_response.provider,
            indexes_suggested=[asdict(a) for a in applications],
            indexes_applied=applied,
            indexes_failed=failed,
            query_results=[asdict(qr) for qr in query_results],
            total_queries=total,
            queries_improved=improved,
            queries_using_new_index=new_index,
            avg_latency_before_ms=avg_before,
            avg_latency_after_ms=avg_after,
            speedup_ratio=speedup,
        )

    def _measure_query(
        self,
        db: DBConnector,
        sql: str,
        db_id: str,
        timeout: int,
        runs: int = 3,
    ) -> QueryPerformance:
        """Execute a query multiple times and collect latency + EXPLAIN data."""
        latencies: list[float] = []
        explain_raw = ""
        uses_index = False
        scan_type = "SeqScan"

        try:
            # Warm-up run
            db.execute(sql, timeout=timeout, db_id=db_id)

            # Timed runs
            for _ in range(runs):
                with measure_latency() as ms:
                    db.execute(sql, timeout=timeout, db_id=db_id)
                latencies.append(ms[0])

            # EXPLAIN
            explain_raw = db.explain(sql, db_id=db_id)
            parsed = self._explain_parser.parse(explain_raw)
            uses_index = parsed.uses_index
            scan_type = parsed.scan_type
        except Exception as exc:
            explain_raw = f"ERROR: {exc}"

        median_latency = statistics.median(latencies) if latencies else 0.0

        return QueryPerformance(
            latency_ms=median_latency,
            explain_raw=explain_raw,
            uses_index=uses_index,
            scan_type=scan_type,
        )
