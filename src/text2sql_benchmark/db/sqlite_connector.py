from __future__ import annotations

import sqlite3
from pathlib import Path

from .base import DBConnector


class SQLiteConnector(DBConnector):
    dialect = "sqlite"

    def __init__(self, db_dir: str) -> None:
        self._db_dir = Path(db_dir)
        self._connections: dict[str, sqlite3.Connection] = {}

    def _get_conn(self, db_id: str) -> sqlite3.Connection:
        if db_id not in self._connections:
            db_path = self._db_dir / db_id / f"{db_id}.sqlite"
            self._connections[db_id] = sqlite3.connect(str(db_path))
        return self._connections[db_id]

    def execute(self, sql: str, timeout: int = 30, db_id: str = "") -> list[tuple]:
        conn = self._get_conn(db_id)
        conn.execute(f"PRAGMA busy_timeout = {timeout * 1000}")
        cur = conn.execute(sql)
        return cur.fetchall()

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
