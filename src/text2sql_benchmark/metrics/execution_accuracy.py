from __future__ import annotations


def execution_accuracy(predicted: list[tuple], gold: list[tuple]) -> bool:
    """Compara os conjuntos de resultados ignorando ordem das linhas."""
    return set(predicted) == set(gold)
