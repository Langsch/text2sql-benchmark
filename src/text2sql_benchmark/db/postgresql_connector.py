from __future__ import annotations

import psycopg2

from .base import DBConnector
from .table_map import tabelas_de
from .sql_split import primeiro_statement

_SCHEMA_PADRAO = "public"


class PostgreSQLConnector(DBConnector):
    dialect = "postgresql"

    def __init__(self, url: str, sqlite_dir: str = "") -> None:
        self._conn = psycopg2.connect(url)
        self._conn.autocommit = True
        self._schema_atual: str | None = None
        # Usado so no layout plano, para saber quais tabelas sao de qual db_id.
        self._sqlite_dir = sqlite_dir
        self._schemas: set[str] | None = None

    def _schemas_existentes(self, cur) -> set[str]:
        if self._schemas is None:
            cur.execute(
                "SELECT schema_name FROM information_schema.schemata"
            )
            self._schemas = {linha[0] for linha in cur.fetchall()}
        return self._schemas

    def _usar(self, cur, db_id: str) -> None:
        """Aponta o search_path para o schema do db_id, quando ele existir.

        No layout plano (tudo num schema so) nao ha o que apontar: os nomes de
        tabela do BIRD sao globalmente unicos, entao as queries resolvem
        direto pelo search_path padrao.
        """
        if not db_id or db_id == self._schema_atual:
            return
        if db_id in self._schemas_existentes(cur):
            cur.execute(f'SET search_path TO "{db_id}", {_SCHEMA_PADRAO}')
            self._schema_atual = db_id

    def execute(self, sql: str, timeout: int = 30, db_id: str = "") -> list[tuple]:
        with self._conn.cursor() as cur:
            # statement_timeout aborta a query de verdade, ao contrario do
            # busy_timeout do SQLite, que so espera lock.
            cur.execute(f"SET statement_timeout = {timeout * 1000}")
            self._usar(cur, db_id)
            cur.execute(sql)
            return cur.fetchall() if cur.description else []

    def explain(self, sql: str, db_id: str = "") -> str:
        # Quando o modelo devolve mais de um statement, o EXPLAIN so prefixa o
        # primeiro: os demais rodam crus e o cursor termina com o resultado da
        # ultima query, nao com um plano. Ai `row[0]` vem inteiro e o join
        # estoura com "expected str instance, int found", virando system_error
        # numa questao que o modelo ate respondeu. Explicar so o primeiro
        # statement resolve sem mudar a semantica de `execute`, que precisa
        # continuar identica a da rodada do Sonnet.
        primeiro = primeiro_statement(sql)
        with self._conn.cursor() as cur:
            self._usar(cur, db_id)
            cur.execute(f"EXPLAIN (ANALYZE, FORMAT TEXT) {primeiro}")
            rows = cur.fetchall()
        return "\n".join(str(row[0]) for row in rows)

    def get_schema(self, db_id: str) -> str:
        """Reconstroi o DDL a partir do information_schema.

        O PostgreSQL nao expoe o CREATE TABLE original, entao o DDL e montado
        a partir dos catalogos. O formato imita o do SQLite para que o prompt
        fique equivalente entre os SGBDs e a comparacao permaneca valida.
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
            colunas = cur.fetchall()

            if not colunas:
                # Layout plano: os dumps foram carregados todos no mesmo
                # schema. Filtra pelas tabelas que pertencem a este db_id.
                #
                # A comparacao e case-insensitive porque o dump do BIRD
                # converte os nomes para minusculas — o SQLite tem
                # `Player_Attributes` e o PostgreSQL, `player_attributes`.
                nomes = tabelas_de(self._sqlite_dir, db_id) if self._sqlite_dir else ()
                if not nomes:
                    raise ValueError(
                        f"Nenhuma tabela encontrada para {db_id!r} — nem como "
                        "schema proprio, nem no layout plano. Os dumps do BIRD "
                        "foram carregados?"
                    )
                cur.execute(
                    """
                    SELECT table_name, column_name, data_type,
                           character_maximum_length, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE lower(table_name) = ANY(%s)
                      AND table_schema NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY table_name, ordinal_position
                    """,
                    ([n.lower() for n in nomes],),
                )
                colunas = cur.fetchall()
                if not colunas:
                    raise ValueError(
                        f"Tabelas de {db_id!r} nao encontradas no PostgreSQL. "
                        "Os dumps do BIRD foram carregados?"
                    )
                cur.execute(
                    """
                    SELECT tc.table_name, kcu.column_name, tc.constraint_type,
                           ccu.table_name, ccu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                    LEFT JOIN information_schema.constraint_column_usage ccu
                      ON tc.constraint_name = ccu.constraint_name
                     AND tc.table_schema = ccu.table_schema
                    WHERE lower(tc.table_name) = ANY(%s)
                      AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
                    """,
                    ([n.lower() for n in nomes],),
                )
                return _montar_ddl(colunas, cur.fetchall(), aspas='"')

            cur.execute(
                """
                SELECT tc.table_name, kcu.column_name, tc.constraint_type,
                       ccu.table_name, ccu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                LEFT JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                 AND tc.table_schema = ccu.table_schema
                WHERE tc.table_schema = %s
                  AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
                """,
                (db_id,),
            )
            restricoes = cur.fetchall()

        return _montar_ddl(colunas, restricoes, aspas='"')

    def close(self) -> None:
        self._conn.close()


def _montar_ddl(
    colunas: list[tuple], restricoes: list[tuple], aspas: str = "`"
) -> str:
    """Monta CREATE TABLE a partir das linhas dos catalogos.

    Compartilhado entre PostgreSQL e MariaDB: as consultas ao
    information_schema diferem na sintaxe de parametro, mas as tuplas
    resultantes tem o mesmo formato.

    O caractere de citacao importa: o schema no prompt e o exemplo que o
    modelo segue. Mostrar `coluna` (crase) para o PostgreSQL faz o modelo
    gerar SQL invalido, porque ali o identificador citado usa aspas duplas.
    Os bancos do BIRD tem colunas como `Enrollment (K-12)`, que so funcionam
    citadas — entao a escolha do caractere decide se o SQL gerado roda.
    """
    q = aspas
    por_tabela: dict[str, list[str]] = {}
    for tabela, coluna, tipo, tamanho, aceita_nulo, padrao in colunas:
        if tamanho:
            tipo = f"{tipo}({tamanho})"
        linha = f"  {q}{coluna}{q} {tipo.upper()}"
        if aceita_nulo == "NO":
            linha += " NOT NULL"
        if padrao is not None and "nextval" not in str(padrao):
            linha += f" DEFAULT {padrao}"
        por_tabela.setdefault(tabela, []).append(linha)

    pks: dict[str, list[str]] = {}
    fks: dict[str, list[str]] = {}
    for tabela, coluna, tipo, ref_tabela, ref_coluna in restricoes:
        if tipo == "PRIMARY KEY":
            pks.setdefault(tabela, []).append(f"{q}{coluna}{q}")
        elif tipo == "FOREIGN KEY" and ref_tabela:
            fks.setdefault(tabela, []).append(
                f"  FOREIGN KEY ({q}{coluna}{q}) REFERENCES {q}{ref_tabela}{q} ({q}{ref_coluna}{q})"
            )

    blocos: list[str] = []
    for tabela in sorted(por_tabela):
        partes = list(por_tabela[tabela])
        if tabela in pks:
            partes.append(f"  PRIMARY KEY ({','.join(sorted(set(pks[tabela])))})")
        partes.extend(sorted(set(fks.get(tabela, []))))
        blocos.append(f"CREATE TABLE {q}{tabela}{q} (\n" + ",\n".join(partes) + "\n)")
    return "\n\n".join(blocos)
