from __future__ import annotations

import uuid
from pathlib import Path

from rich.console import Console
from rich.progress import track

from ..config import BenchmarkConfig
from ..dataset import BirdLoader, BirdInstance
from ..db import DBConnector, PostgreSQLConnector, MariaDBConnector, SQLiteConnector
from ..llm import LLMConnector, AnthropicConnector, OpenAIConnector, GoogleConnector, GroqConnector
from ..metrics import execution_accuracy, exact_match, measure_latency
from ..metrics.explain_parsers import PostgreSQLExplainParser, MariaDBExplainParser, SQLiteExplainParser
from ..prompt import BirdPromptBuilder
from ..storage import BenchmarkResult, ResultsStore

console = Console()

_EXPLAIN_PARSERS = {
    "postgresql": PostgreSQLExplainParser(),
    "mariadb": MariaDBExplainParser(),
    "sqlite": SQLiteExplainParser(),
}


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


def _build_db_connectors(cfg: BenchmarkConfig) -> list[DBConnector]:
    connectors: list[DBConnector] = []
    for db_cfg in cfg.databases:
        if not db_cfg.url:
            continue
        if db_cfg.dialect == "postgresql":
            connectors.append(PostgreSQLConnector(db_cfg.url))
        elif db_cfg.dialect == "mariadb":
            connectors.append(MariaDBConnector(db_cfg.url))
        elif db_cfg.dialect == "sqlite":
            connectors.append(SQLiteConnector(db_cfg.url))
    return connectors


class BenchmarkRunner:
    def __init__(self, cfg: BenchmarkConfig) -> None:
        self._cfg = cfg
        self._loader = BirdLoader()
        self._prompt_builder = BirdPromptBuilder()
        self._store = ResultsStore(cfg.output_dir)

    def run(
        self,
        limit: int | None = None,
        difficulty: str | None = None,
        db_id: str | None = None,
    ) -> Path:
        run_id = str(uuid.uuid4())[:8]
        instances = list(
            self._loader.load(self._cfg.bird_data_path)
            and self._loader.iter_instances(difficulty=difficulty, limit=limit, db_id=db_id)
        )
        llms = _build_llm_connectors(self._cfg)
        dbs = _build_db_connectors(self._cfg)

        console.print(f"[bold]Run {run_id}[/bold] — {len(instances)} instâncias × {len(llms)} LLMs × {len(dbs)} SGBDs")

        for instance in track(instances, description="Processando..."):
            for db in dbs:
                schema = db.get_schema(instance.db_id)
                prompt = self._prompt_builder.build(
                    instance, schema, db.dialect, self._cfg.use_evidence
                )
                for llm in llms:
                    result = self._run_single(instance, llm, db, prompt)
                    self._store.add(result)

        path = self._store.save(run_id)
        console.print(f"[green]Resultados salvos em {path}[/green]")
        return path

    def _run_single(
        self,
        instance: BirdInstance,
        llm: LLMConnector,
        db: DBConnector,
        prompt: str,
    ) -> BenchmarkResult:
        error: str | None = None
        sql_generated = ""
        ex = False
        em = False
        latency_ms = 0.0
        explain_raw = ""
        explain_parsed: dict = {}

        try:
            llm_response = llm.generate(prompt)
            sql_generated = llm_response.sql

            with measure_latency() as ms:
                pred_rows = db.execute(sql_generated, timeout=self._cfg.timeout_seconds)
            latency_ms = ms[0]

            gold_rows = db.execute(instance.sql_gold, timeout=self._cfg.timeout_seconds)
            ex = execution_accuracy(pred_rows, gold_rows)
            em = exact_match(sql_generated, instance.sql_gold)

            explain_raw = db.explain(sql_generated)
            parser = _EXPLAIN_PARSERS[db.dialect]
            parsed = parser.parse(explain_raw)
            explain_parsed = {
                "scan_type": parsed.scan_type,
                "total_cost": parsed.total_cost,
                "actual_rows": parsed.actual_rows,
                "uses_index": parsed.uses_index,
            }
        except Exception as exc:
            error = str(exc)

        return BenchmarkResult(
            instance_id=instance.instance_id,
            db_id=instance.db_id,
            difficulty=instance.difficulty,
            model=llm.model_name,
            sgbd=db.dialect,
            sql_generated=sql_generated,
            sql_gold=instance.sql_gold,
            execution_accuracy=ex,
            exact_match=em,
            latency_ms=latency_ms,
            explain_raw=explain_raw,
            explain_parsed=explain_parsed,
            error=error,
        )
