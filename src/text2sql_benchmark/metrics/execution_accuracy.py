from __future__ import annotations

from typing import Any


def _hashavel(valor: Any) -> Any:
    """Torna um valor comparavel por conjunto.

    O PostgreSQL devolve `ARRAY_AGG` e afins como lista Python, que nao entra
    em `set()`. Sem esta conversao a comparacao levantava
    "unhashable type: 'list'", a questao virava `system_error` e a resposta do
    modelo era descartada — mesmo estando correta.
    """
    if isinstance(valor, (list, tuple)):
        return tuple(_hashavel(v) for v in valor)
    if isinstance(valor, dict):  # JSON/JSONB
        return tuple(sorted((k, _hashavel(v)) for k, v in valor.items()))
    if isinstance(valor, (set, frozenset)):
        return frozenset(_hashavel(v) for v in valor)
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return bytes(valor)
    return valor


def execution_accuracy(predicted: list[tuple], gold: list[tuple]) -> bool:
    """Compara os conjuntos de resultados ignorando ordem das linhas."""
    return {_hashavel(linha) for linha in predicted} == {
        _hashavel(linha) for linha in gold
    }
