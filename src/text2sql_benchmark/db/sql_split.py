from __future__ import annotations

import re

# Ponto-e-virgula fora de aspas simples, duplas ou crases.
_SEPARADOR = re.compile(r"""(?:[^;'"`]|'[^']*'|"[^"]*"|`[^`]*`)+""")


def primeiro_statement(sql: str) -> str:
    """Primeiro comando de um SQL que pode conter varios.

    O prompt pede uma consulta so, mas modelos as vezes devolvem duas. Para
    `EXPLAIN` isso e fatal: o prefixo vale so para o primeiro comando e o
    cursor acaba com o resultado do ultimo, nao com um plano.
    """
    partes = _SEPARADOR.findall(sql)
    for parte in partes:
        if parte.strip():
            return parte.strip()
    return sql.strip()
