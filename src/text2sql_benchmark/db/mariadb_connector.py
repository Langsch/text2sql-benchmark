from __future__ import annotations

import pymysql
import pymysql.cursors

from .base import DBConnector


class MariaDBConnector(DBConnector):
    dialect = "mariadb"

    def __init__(self, url: str) -> None:
        # url format: mysql+mariadb://user:pass@host:port/db
        from urllib.parse import urlparse
        parsed = urlparse(url.replace("mysql+mariadb://", "mysql://"))
        self._conn = pymysql.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip("/"),
            cursorclass=pymysql.cursors.Cursor,
            autocommit=True,
        )

    def execute(self, sql: str, timeout: int = 30) -> list[tuple]:
        with self._conn.cursor() as cur:
            cur.execute(f"SET SESSION max_statement_time = {timeout}")
            cur.execute(sql)
            return list(cur.fetchall()) if cur.description else []

    def explain(self, sql: str) -> str:
        with self._conn.cursor() as cur:
            cur.execute(f"EXPLAIN ANALYZE {sql}")
            rows = cur.fetchall()
        return "\n".join(str(row) for row in rows)

    def get_schema(self, db_id: str) -> str:
        # TODO: gerar DDL a partir do information_schema para o db_id
        raise NotImplementedError

    def close(self) -> None:
        self._conn.close()
