from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .base import DBConnector


class QueryTimeout(Exception):
    """Query abortada por exceder o tempo limite.

    Distinta de erro de SQL: a query e valida, so nao termina a tempo. Para o
    benchmark isso e resultado de performance, nao falha de corretude.
    """

    def __init__(self, segundos: int, decorrido_ms: float) -> None:
        super().__init__(f"Query excedeu {segundos}s (rodou {decorrido_ms:.0f}ms)")
        self.segundos = segundos
        self.decorrido_ms = decorrido_ms


class SQLiteConnector(DBConnector):
    dialect = "sqlite"

    def __init__(self, db_dir: str) -> None:
        self._db_dir = Path(db_dir)
        self._connections: dict[str, sqlite3.Connection] = {}

    def _get_conn(self, db_id: str) -> sqlite3.Connection:
        if db_id not in self._connections:
            db_path = self._db_dir / db_id / f"{db_id}.sqlite"
            if not db_path.exists():
                raise FileNotFoundError(
                    f"Banco SQLite não encontrado: {db_path}\n"
                    f"Verifique se SQLITE_DB_DIR={self._db_dir} está correto no .env"
                )
            self._connections[db_id] = sqlite3.connect(str(db_path))
        return self._connections[db_id]

    def execute(self, sql: str, timeout: int = 30, db_id: str = "") -> list[tuple]:
        conn = self._get_conn(db_id)
        # busy_timeout so controla espera por lock; nao interrompe uma query em
        # execucao. Para ter teto de tempo real e preciso o progress handler,
        # que o SQLite chama a cada N instrucoes da VM — retornar diferente de
        # zero ali aborta a query em andamento.
        conn.execute(f"PRAGMA busy_timeout = {timeout * 1000}")
        limite = time.perf_counter() + timeout
        estourou = False

        def _vigia() -> int:
            nonlocal estourou
            if time.perf_counter() > limite:
                estourou = True
                return 1
            return 0

        inicio = time.perf_counter()
        conn.set_progress_handler(_vigia, 10_000)
        try:
            cur = conn.execute(sql)
            return cur.fetchall()
        except sqlite3.OperationalError:
            if estourou:
                raise QueryTimeout(
                    timeout, (time.perf_counter() - inicio) * 1000
                ) from None
            raise
        finally:
            conn.set_progress_handler(None, 0)

    def explain(self, sql: str, db_id: str = "") -> str:
        conn = self._get_conn(db_id)
        rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
        return "\n".join(str(row) for row in rows)

    def get_schema(self, db_id: str) -> str:
        conn = self._get_conn(db_id)
        rows = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        ).fetchall()
        return "\n\n".join(row[0] for row in rows)

    def close(self) -> None:
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()
