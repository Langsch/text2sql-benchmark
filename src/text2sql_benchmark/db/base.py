from __future__ import annotations

from abc import ABC, abstractmethod


class DBConnector(ABC):
    dialect: str  # "postgresql" | "mariadb" | "sqlite"

    @abstractmethod
    def execute(self, sql: str, timeout: int = 30) -> list[tuple]: ...

    @abstractmethod
    def explain(self, sql: str) -> str:
        """Retorna a saída bruta do EXPLAIN (ANALYZE) específica de cada SGBD."""
        ...

    @abstractmethod
    def get_schema(self, db_id: str) -> str:
        """Retorna o DDL das tabelas do banco como string, usado no prompt."""
        ...

    @abstractmethod
    def close(self) -> None: ...

    def __enter__(self) -> "DBConnector":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
