from __future__ import annotations

import re
import shutil
import statistics
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import track

from ..config import BenchmarkConfig
from ..dataset import BirdLoader, BirdInstance
from ..db import SQLiteConnector
from ..llm import LLMConnector, AnthropicConnector, OpenAIConnector, GoogleConnector, GroqConnector
from ..metrics import measure_latency
from ..metrics.explain_parsers import SQLiteExplainParser
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
_CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+\s+ON\s+\w+\s*\([^)]+\)\s*;?",
    re.IGNORECASE,
)

_explain_parser = SQLiteExplainParser()


def _build_run_id(db_id: str | None, difficulty: str | None) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    parts = [ts, "index", db_id or "all"]
    if difficulty:
        parts.append(difficulty)
    return "_".join(parts)


def _build_llm_connectors(cfg: BenchmarkConfig) -> list[LLMConnector]:
    connectors: list[LLMConnector] = []
    for llm_cfg in cfg.llms:
        if not llm_cfg.api_key:
            continue
        if "claude" in llm_cfg.model_name:
            connectors.append(AnthropicConnector(llm_cfg.api_key))
        elif "gpt" in llm_cfg.model_name:
            connectors.append(OpenAIConnector(llm_cfg.api_key))
        elif "gemini" in llm_cfg.model_name:
            connectors.append(GoogleConnector(llm_cfg.api_key))
        else:
            connectors.append(GroqConnector(llm_cfg.model_name, llm_cfg.api_key))
    return connectors


def parse_index_statements(raw: str) -> list[str]:
    """Extract CREATE INDEX statements from raw LLM response text."""
    text = _THINK_RE.sub("", raw).strip()
    fences = _FENCE_RE.findall(text)
    if fences:
        text = "\n".join(fences)
    statements = _CREATE_INDEX_RE.findall(text)
    # Normalize: ensure each ends with a semicolon
    return [s.rstrip(";").strip() + ";" for s in statements]


def _get_sqlite_db_dir(cfg: BenchmarkConfig) -> str:
    for db_cfg in cfg.databases:
        if db_cfg.dialect == "sqlite":
            return db_cfg.url
    raise ValueError("No SQLite database configured in .env (SQLITE_DB_DIR)")


class IndexBenchmarkRunner:
    def __init__(self, cfg: BenchmarkConfig) -> None:
        self._cfg = cfg
        self._loader = BirdLoader()
        self._prompt_builder = IndexPromptBuilder()
        self._store = IndexResultsStore(cfg.output_dir / "index_runs")
        self._db_dir = Path(_get_sqlite_db_dir(cfg))

    def run(
        self,
        limit: int | None = None,
        difficulty: str | None = None,
        db_id: str | None = None,
        model: str | None = None,
    ) -> Path:
        run_id = _build_run_id(db_id, difficulty)

        # Load BIRD instances (SQLite only)
        self._loader.load(self._cfg.bird_data_path, dialect="sqlite")
        instances = list(
            self._loader.iter_instances(difficulty=difficulty, limit=limit, db_id=db_id)
        )

        # Group instances by db_id
        by_db: dict[str, list[BirdInstance]] = defaultdict(list)
        for inst in instances:
            by_db[inst.db_id].append(inst)

        llms = _build_llm_connectors(self._cfg)
        if model:
            llms = [l for l in llms if l.model_name == model]

        total_combos = len(by_db) * len(llms)
        console.print(
            f"[bold]Run {run_id}[/bold] — "
            f"{len(by_db)} databases × {len(llms)} LLMs = {total_combos} combinations, "
            f"{len(instances)} total queries"
        )

        original_db = SQLiteConnector(str(self._db_dir))

        combo_items = [
            (current_db_id, llm)
            for current_db_id in sorted(by_db)
            for llm in llms
        ]

        for current_db_id, llm in track(combo_items, description="Index benchmark..."):
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
        original_db: SQLiteConnector,
    ) -> IndexBenchmarkResult:
        console.print(f"  [cyan]{db_id}[/cyan] × [yellow]{llm.model_name}[/yellow]")

        # --- Step 1: Build prompt and call LLM ---
        schema = original_db.get_schema(db_id)
        gold_queries = [inst.sql_gold for inst in instances]
        prompt = self._prompt_builder.build(schema, gold_queries, db_id)

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
                error=str(exc),
            )

        raw_response = llm_response.sql
        index_statements = parse_index_statements(raw_response)
        console.print(f"    Indexes suggested: {len(index_statements)}")

        # --- Step 2: Copy database and apply indexes ---
        copy_path = self._copy_database(db_id, llm.model_name)
        applications = self._apply_indexes(copy_path, index_statements)

        applied = sum(1 for a in applications if a.success)
        failed = sum(1 for a in applications if not a.success)
        console.print(f"    Applied: {applied}, Failed: {failed}")

        # --- Step 3: Benchmark queries before and after ---
        indexed_db_dir = copy_path.parent.parent  # .../tmp_dbs/{db_id}/{db}.sqlite → .../tmp_dbs/
        indexed_db = SQLiteConnector(str(indexed_db_dir))

        query_results: list[QueryResult] = []
        for inst in instances:
            qr = self._benchmark_query(inst, original_db, indexed_db, db_id)
            query_results.append(qr)

        indexed_db.close()

        # Clean up the copy
        try:
            copy_path.unlink()
        except OSError:
            pass

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

    def _copy_database(self, db_id: str, model_name: str) -> Path:
        """Copy the original .sqlite to a temporary location for indexing."""
        original = self._db_dir / db_id / f"{db_id}.sqlite"
        tmp_dir = self._cfg.output_dir / "index_runs" / "tmp_dbs" / db_id
        tmp_dir.mkdir(parents=True, exist_ok=True)
        copy_path = tmp_dir / f"{db_id}.sqlite"
        shutil.copy2(str(original), str(copy_path))
        return copy_path

    def _apply_indexes(
        self, db_path: Path, statements: list[str]
    ) -> list[IndexApplication]:
        """Apply CREATE INDEX statements on the copied database."""
        import sqlite3

        results: list[IndexApplication] = []
        conn = sqlite3.connect(str(db_path))
        try:
            for stmt in statements:
                try:
                    conn.execute(stmt)
                    conn.commit()
                    results.append(IndexApplication(statement=stmt, success=True))
                except Exception as exc:
                    results.append(
                        IndexApplication(statement=stmt, success=False, error=str(exc))
                    )
        finally:
            conn.close()
        return results

    def _benchmark_query(
        self,
        instance: BirdInstance,
        original_db: SQLiteConnector,
        indexed_db: SQLiteConnector,
        db_id: str,
        runs: int = 3,
    ) -> QueryResult:
        """Run a gold query on both original and indexed DBs, collecting performance data."""
        sql = instance.sql_gold
        timeout = self._cfg.timeout_seconds

        before = self._measure_query(original_db, sql, db_id, timeout, runs)
        after = self._measure_query(indexed_db, sql, db_id, timeout, runs)

        improved = after.latency_ms < before.latency_ms
        new_index_used = after.uses_index and not before.uses_index

        return QueryResult(
            instance_id=instance.instance_id,
            sql=sql,
            difficulty=instance.difficulty,
            before=before,
            after=after,
            improved=improved,
            new_index_used=new_index_used,
        )

    def _measure_query(
        self,
        db: SQLiteConnector,
        sql: str,
        db_id: str,
        timeout: int,
        runs: int,
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
            parsed = _explain_parser.parse(explain_raw)
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
