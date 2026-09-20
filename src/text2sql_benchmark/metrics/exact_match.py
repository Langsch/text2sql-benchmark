from __future__ import annotations

import re

# Ponto-e-virgula final, com espacos em volta. So o do fim: um `;` no meio
# separa comandos e e diferenca real, nao cosmetica.
_PONTO_FINAL = re.compile(r"\s*;\s*$")


def _normalize(sql: str) -> str:
    sql = sql.lower().strip()
    # O terminador nao muda o significado da consulta, e as queries gabarito do
    # BIRD nao o usam. Sem remove-lo, um modelo que sempre encerra com `;`
    # tinha Exact Match estruturalmente zero, por diferenca puramente
    # tipografica: o Luna terminava 500/500 assim e o DeepSeek 498/500.
    sql = _PONTO_FINAL.sub("", sql)
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r"[`'\"]", "", sql)
    return sql


def exact_match(predicted: str, gold: str) -> bool:
    """Compara strings SQL após normalização básica.

    Normaliza caixa, espacos, aspas e o ponto-e-virgula final — diferencas que
    nao alteram a consulta. Nao normaliza aliases, ordem de clausulas nem
    parenteses redundantes: essas sao escolhas de escrita, e distingui-las e o
    proposito da metrica.
    """
    return _normalize(predicted) == _normalize(gold)
