from __future__ import annotations

import re


def _normalize(sql: str) -> str:
    sql = sql.lower().strip()
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r"[`'\"]", "", sql)
    return sql


def exact_match(predicted: str, gold: str) -> bool:
    """Compara strings SQL após normalização básica (case, whitespace, aspas)."""
    return _normalize(predicted) == _normalize(gold)
