from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import track

from ..config import BenchmarkConfig
from ..dataset import BirdLoader, BirdInstance
from ..db import DBConnector, PostgreSQLConnector, MariaDBConnector, SQLiteConnector
from ..db.sqlite_connector import QueryTimeout
from ..llm import LLMConnector, AnthropicConnector, OpenAIConnector, GoogleConnector, GroqConnector
from ..metrics import execution_accuracy, exact_match, measure_latency
from ..metrics.explain_parsers import PostgreSQLExplainParser, MariaDBExplainParser, SQLiteExplainParser
from ..prompt import BirdPromptBuilder
from ..storage import BenchmarkResult, ResultsStore

console = Console()


# Erros de SQL nos tres drivers. Cada um define dezenas de subclasses — o
# psycopg2 levanta `SyntaxError`, `UndefinedColumn`, `UndefinedTable` etc., que
# herdam de `ProgrammingError`. Checar so o nome exato da classe deixava tudo
# isso cair em "system_error" e atribuia ao ambiente um erro do modelo.
_ERROS_DE_SQL = {
    "OperationalError",      # sqlite3, psycopg2, pymysql
    "ProgrammingError",      # psycopg2, pymysql
    "DatabaseError",
    "IntegrityError",
    "DataError",
    "InternalError",
    "NotSupportedError",
    "Warning",
}

def _classificar_erro(exc: Exception) -> str:
    """Distingue SQL invalido de falha de infraestrutura.

    Importa para o TCC: um SQL invalido e limitacao do modelo e conta como
    resultado; uma queda de conexao e problema do ambiente e nao deve ser
    atribuida ao modelo.

    A checagem percorre a hierarquia de classes porque os drivers derivam
    erros especificos das classes da DB-API: `psycopg2.errors.SyntaxError`
    herda de `ProgrammingError`, e olhar so o nome da classe concreta perderia
    a classificacao.
    """
    for classe in type(exc).__mro__:
        nome = classe.__name__
        if nome == "InterfaceError":
            return "system_error"
        if nome in _ERROS_DE_SQL:
            return "sql_error"
    return "system_error"


def _build_run_id(sgbd: str | None, db_id: str | None, difficulty: str | None) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    parts = [ts, sgbd or "sqlite", db_id or "all"]
    if difficulty:
        parts.append(difficulty)
    return "_".join(parts)

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
            connectors.append(AnthropicConnector(llm_cfg.model_name, llm_cfg.api_key))
        elif "gpt" in llm_cfg.model_name:
            connectors.append(OpenAIConnector(llm_cfg.model_name, llm_cfg.api_key))
        elif "gemini" in llm_cfg.model_name:
            connectors.append(GoogleConnector(llm_cfg.model_name, llm_cfg.api_key))
        else:
            connectors.append(GroqConnector(llm_cfg.model_name, llm_cfg.api_key))
    return connectors


def _build_db_connectors(cfg: BenchmarkConfig, sgbd: str | None = None) -> list[DBConnector]:
    # PostgreSQL e MariaDB usam os .sqlite como fonte do mapa tabela->db_id,
    # necessario caso os dumps do BIRD tenham sido carregados num schema unico.
    sqlite_dir = next(
        (d.url for d in cfg.databases if d.dialect == "sqlite"), ""
    )
    connectors: list[DBConnector] = []
    for db_cfg in cfg.databases:
        if sgbd and db_cfg.dialect != sgbd:
            continue
        if not db_cfg.url:
            continue
        if db_cfg.dialect == "postgresql":
            connectors.append(PostgreSQLConnector(db_cfg.url, sqlite_dir))
        elif db_cfg.dialect == "mariadb":
            connectors.append(MariaDBConnector(db_cfg.url, sqlite_dir))
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
        sgbd: str | None = None,
        model: str | None = None,
        resume: Path | None = None,
    ) -> Path:
        run_id = _build_run_id(sgbd, db_id, difficulty)

        # Retomada: reaproveita o que ja foi pago numa rodada interrompida.
        # A chave e (instance_id, model, sgbd) — a mesma questao pode aparecer
        # para modelos ou SGBDs diferentes.
        ja_feitas: set[tuple] = set()
        if resume:
            self._store.load(Path(resume))
            descartados = self._store.descartar("llm_error")
            if descartados:
                console.print(
                    f"[yellow]{descartados} resultados descartados "
                    "(falha de API, nao do modelo) — serao refeitos.[/yellow]"
                )
            anteriores = list(self._store._results)
            for r in anteriores:
                # `llm_error` significa que a chamada nao chegou a acontecer —
                # cota esgotada, rede fora. Nao e resultado e precisa ser
                # refeito. Um SQL invalido ou um timeout, sim, sao resultado.
                if r.error_type == "llm_error":
                    continue
                ja_feitas.add((r.instance_id, r.model, r.sgbd))
            run_id = Path(resume).stem
            console.print(
                f"[cyan]Retomando {run_id}: {len(ja_feitas)} resultados "
                "aproveitados.[/cyan]"
            )

        self._store.begin(run_id)
        dialect = sgbd or "sqlite"
        instances = list(
            self._loader.load(self._cfg.bird_data_path, dialect=dialect)
            and self._loader.iter_instances(difficulty=difficulty, limit=limit, db_id=db_id)
        )
        llms = _build_llm_connectors(self._cfg)
        if model:
            llms = [l for l in llms if l.model_name == model]
            if not llms:
                disponiveis = [
                    c.model_name for c in _build_llm_connectors(self._cfg)
                ]
                raise ValueError(
                    f"Modelo {model!r} nao tem chave configurada. "
                    f"Disponiveis: {disponiveis}"
                )
        dbs = _build_db_connectors(self._cfg, sgbd=sgbd)
        if not dbs:
            raise ValueError(f"Nenhum SGBD configurado para sgbd={sgbd!r}")

        console.print(f"[bold]Run {run_id}[/bold] — {len(instances)} instâncias × {len(llms)} LLMs × {len(dbs)} SGBDs")

        for instance in track(instances, description="Processando..."):
            for db in dbs:
                pendentes = [
                    l for l in llms
                    if (instance.instance_id, l.model_name, db.dialect) not in ja_feitas
                ]
                if not pendentes:
                    continue
                schema = db.get_schema(instance.db_id)
                prompt = self._prompt_builder.build(
                    instance, schema, db.dialect, self._cfg.use_evidence
                )
                for llm in pendentes:
                    result = self._run_single(instance, llm, db, prompt, db_id=instance.db_id)
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
        db_id: str = "",
    ) -> BenchmarkResult:
        error: str | None = None
        error_type: str | None = None
        timed_out_after_ms = 0.0
        sql_generated = ""
        ex = False
        em = False
        latency_ms = 0.0
        explain_raw = ""
        explain_parsed: dict = {}

        # A chamada ao LLM fica num try proprio: falha de API nao pode ser
        # confundida com SQL invalido gerado pelo modelo.
        try:
            llm_response = llm.generate(prompt)
            sql_generated = llm_response.sql
        except Exception as exc:
            return BenchmarkResult(
                instance_id=instance.instance_id,
                db_id=instance.db_id,
                difficulty=instance.difficulty,
                model=llm.model_name,
                sgbd=db.dialect,
                sql_generated="",
                sql_gold=instance.sql_gold,
                execution_accuracy=False,
                exact_match=False,
                latency_ms=0.0,
                explain_raw="",
                explain_parsed={},
                prompt=prompt,
                error=str(exc),
                error_type="llm_error",
            )

        try:
            with measure_latency() as ms:
                pred_rows = db.execute(sql_generated, timeout=self._cfg.timeout_seconds, db_id=db_id)
            latency_ms = ms[0]

            gold_rows = db.execute(instance.sql_gold, timeout=self._cfg.timeout_seconds, db_id=db_id)
            ex = execution_accuracy(pred_rows, gold_rows)
            em = exact_match(sql_generated, instance.sql_gold)

            explain_raw = db.explain(sql_generated, db_id=db_id)
            parser = _EXPLAIN_PARSERS[db.dialect]
            parsed = parser.parse(explain_raw)
            explain_parsed = {
                "scan_type": parsed.scan_type,
                "total_cost": parsed.total_cost,
                "actual_rows": parsed.actual_rows,
                "uses_index": parsed.uses_index,
            }
        except QueryTimeout as exc:
            error = str(exc)
            error_type = "timeout"
            timed_out_after_ms = exc.decorrido_ms
        except Exception as exc:
            error = str(exc)
            error_type = _classificar_erro(exc)

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
            prompt=prompt,
            error=error,
            error_type=error_type,
            timed_out_after_ms=timed_out_after_ms,
        )
