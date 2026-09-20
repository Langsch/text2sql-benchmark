"""Mapa de qual tabela pertence a qual banco do BIRD.

O BIRD garante nomes de tabela globalmente unicos entre os 11 bancos — foram
verificados 75 nomes distintos, zero colisoes. Por isso os dumps podem ser
carregados de duas formas:

  a) um schema (PostgreSQL) ou database (MariaDB) por db_id;
  b) tudo junto num unico schema/database, sem conflito.

A documentacao do BIRD e ambigua sobre qual das duas o dump usa. Este mapa
permite que `get_schema()` funcione nos dois casos: se o layout (a) nao for
encontrado, o codigo cai para (b) filtrando pelos nomes de tabela do db_id.

O mapa e derivado dos arquivos .sqlite, que sao a fonte canonica.
"""

from __future__ import annotations

import functools
import glob
import os
import sqlite3
from pathlib import Path


@functools.lru_cache(maxsize=None)
def tabelas_por_banco(db_dir: str) -> dict[str, tuple[str, ...]]:
    """Le os .sqlite e devolve {db_id: (tabela, ...)}."""
    mapa: dict[str, tuple[str, ...]] = {}
    for arquivo in sorted(glob.glob(str(Path(db_dir) / "*" / "*.sqlite"))):
        db_id = os.path.basename(os.path.dirname(arquivo))
        conn = sqlite3.connect(f"file:{arquivo}?mode=ro", uri=True)
        try:
            nomes = [
                linha[0]
                for linha in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name"
                )
            ]
        finally:
            conn.close()
        if nomes:
            mapa[db_id] = tuple(nomes)
    return mapa


def tabelas_de(db_dir: str, db_id: str) -> tuple[str, ...]:
    """Nomes das tabelas de um db_id. Vazio se desconhecido."""
    return tabelas_por_banco(db_dir).get(db_id, ())
