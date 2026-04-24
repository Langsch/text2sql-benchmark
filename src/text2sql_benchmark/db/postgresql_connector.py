from __future__ import annotations

import psycopg2

from .base import DBConnector


class PostgreSQLConnector(DBConnector):
    dialect = "postgresql"

    def __init__(self, url: str) -> None:
        self._conn = psycopg2.connect(url)
        self._conn.autocommit = True

    def execute(self, sql: str, timeout: int = 30) -> list[tuple]:
        with self._conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {timeout * 1000}")
            cur.execute(sql)
            return cur.fetchall() if cur.description else []

    def explain(self, sql: str) -> str:
        with self._conn.cursor() as cur:
            cur.execute(f"EXPLAIN (ANALYZE, FORMAT TEXT) {sql}")
            rows = cur.fetchall()
        return "\n".join(row[0] for row in rows)

    def get_schema(self, db_id: str) -> str:
        # TODO: gerar DDL a partir do information_schema para o db_id
        raise NotImplementedError

    def close(self) -> None:
        self._conn.close()
