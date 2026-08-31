from __future__ import annotations

from abc import ABC, abstractmethod


class DBConnector(ABC):
    dialect: str  # "postgresql" | "mariadb" | "sqlite"

    @abstractmethod
    def execute(self, sql: str, timeout: int = 30, db_id: str = "") -> list[tuple]:
        """Executa `sql` no banco `db_id`, respeitando o tempo limite.

        O BIRD tem 11 bancos e o benchmark alterna entre eles, por isso todo
        metodo recebe `db_id`. No SQLite ele seleciona o arquivo; no
        PostgreSQL, o schema; no MariaDB, o database.
        """
        ...

    @abstractmethod
    def explain(self, sql: str, db_id: str = "") -> str:
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
