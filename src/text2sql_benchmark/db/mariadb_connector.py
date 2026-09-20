from __future__ import annotations

from urllib.parse import urlparse

import pymysql
import pymysql.cursors

from .base import DBConnector
from .postgresql_connector import _montar_ddl
from .table_map import tabelas_de


class MariaDBConnector(DBConnector):
    dialect = "mariadb"

    def __init__(self, url: str, sqlite_dir: str = "") -> None:
        # url no formato: mysql+mariadb://user:pass@host:port/db
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
        self._db_atual: str | None = None
        # Usado so no layout plano, para saber quais tabelas sao de qual db_id.
        self._sqlite_dir = sqlite_dir
        self._databases: set[str] | None = None

    def _databases_existentes(self, cur) -> set[str]:
        if self._databases is None:
            cur.execute("SELECT schema_name FROM information_schema.schemata")
            self._databases = {linha[0] for linha in cur.fetchall()}
        return self._databases

    def _usar(self, cur, db_id: str) -> None:
        """Troca o database ativo, quando existir um por db_id.

        No layout plano (tudo num database so) nao ha o que trocar: os nomes de
        tabela do BIRD sao globalmente unicos e resolvem no database corrente.
        """
        if not db_id or db_id == self._db_atual:
            return
        if db_id in self._databases_existentes(cur):
            cur.execute(f"USE `{db_id}`")
            self._db_atual = db_id

    def execute(self, sql: str, timeout: int = 30, db_id: str = "") -> list[tuple]:
        with self._conn.cursor() as cur:
            # max_statement_time e em segundos no MariaDB e aborta a query.
            cur.execute(f"SET SESSION max_statement_time = {timeout}")
            self._usar(cur, db_id)
            cur.execute(sql)
            return list(cur.fetchall()) if cur.description else []

    def explain(self, sql: str, db_id: str = "") -> str:
        """Plano de execucao com estatisticas reais.

        O MariaDB nao implementa `EXPLAIN ANALYZE` (isso e MySQL 8); a forma
        equivalente e `ANALYZE FORMAT=JSON`, que executa a query e devolve
        custo, linhas estimadas e reais, e uso de indice por tabela.
        """
        with self._conn.cursor() as cur:
            self._usar(cur, db_id)
            cur.execute(f"ANALYZE FORMAT=JSON {sql}")
            rows = cur.fetchall()
        return "\n".join(str(row[0]) for row in rows) if rows else ""

    def get_schema(self, db_id: str) -> str:
        """Reconstroi o DDL a partir do information_schema.

        No MySQL/MariaDB `table_schema` e o nome do database. O DDL sai no
        mesmo formato do PostgreSQL e do SQLite para manter o prompt
        equivalente entre os SGBDs.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name, column_name, data_type,
                       character_maximum_length, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                (db_id,),
            )
            colunas = list(cur.fetchall())

            if not colunas:
                # Layout plano: tudo carregado no mesmo database. Filtra pelas
                # tabelas que pertencem a este db_id.
                nomes = tabelas_de(self._sqlite_dir, db_id) if self._sqlite_dir else ()
                if not nomes:
                    raise ValueError(
                        f"Nenhuma tabela encontrada para {db_id!r} — nem como "
                        "database proprio, nem no layout plano. Os dumps do "
                        "BIRD foram carregados?"
                    )
                marcadores = ",".join(["%s"] * len(nomes))
                cur.execute(
                    f"""
                    SELECT table_name, column_name, data_type,
                           character_maximum_length, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE LOWER(table_name) IN ({marcadores})
                      AND table_schema NOT IN
                          ('information_schema','mysql','performance_schema','sys')
                    ORDER BY table_name, ordinal_position
                    """,
                    tuple(n.lower() for n in nomes),
                )
                colunas = list(cur.fetchall())
                if not colunas:
                    raise ValueError(
                        f"Tabelas de {db_id!r} nao encontradas no MariaDB. "
                        "Os dumps do BIRD foram carregados?"
                    )
                cur.execute(
                    f"""
                    SELECT tc.table_name, kcu.column_name, tc.constraint_type,
                           kcu.referenced_table_name, kcu.referenced_column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                     AND tc.table_name = kcu.table_name
                    WHERE LOWER(tc.table_name) IN ({marcadores})
                      AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
                    """,
                    tuple(n.lower() for n in nomes),
                )
                return _montar_ddl(colunas, list(cur.fetchall()))

            cur.execute(
                """
                SELECT tc.table_name, kcu.column_name, tc.constraint_type,
                       kcu.referenced_table_name, kcu.referenced_column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                 AND tc.table_name = kcu.table_name
                WHERE tc.table_schema = %s
                  AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
                """,
                (db_id,),
            )
            restricoes = list(cur.fetchall())

        return _montar_ddl(colunas, restricoes)

    def close(self) -> None:
        self._conn.close()
