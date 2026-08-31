"""Extracao do SQL da resposta bruta de um LLM.

Os modelos costumam devolver o SQL dentro de cercas markdown e, quando tem
raciocinio visivel, precedido de um bloco <think>. Passar esse texto direto
para o banco gera erro de sintaxe e contamina a metrica de acuracia: a questao
aparece como falha do modelo quando na verdade e falha de parsing.
"""

from __future__ import annotations

import re

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
# Cerca aberta sem fechamento: acontece quando a resposta e truncada.
_OPEN_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*)", re.DOTALL | re.IGNORECASE)


def extract_sql(text: str) -> str:
    """Devolve apenas o SQL contido em `text`."""
    if not text:
        return ""

    cleaned = _THINK_RE.sub("", text).strip()

    fences = _FENCE_RE.findall(cleaned)
    if fences:
        # Varias cercas: o modelo pode ter comentado entre elas. Junta todas.
        return "\n".join(f.strip() for f in fences if f.strip()).strip()

    aberta = _OPEN_FENCE_RE.match(cleaned)
    if aberta:
        return aberta.group(1).strip()

    return cleaned
