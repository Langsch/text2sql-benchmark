"""Garante que os nomes usados dentro dos runners existem no modulo.

Motivo: ao unificar a fabrica de conectores, o import dos conectores saiu do
`index_runner` mas uma referencia a `GroqConnector` continuou viva num ramo que
so executa a partir do segundo banco. Os testes passavam, o import do modulo
passava, e a rodada quebrou com NameError depois de 20 minutos de Etapa 1 ja
paga.
"""
import ast
import builtins
from pathlib import Path

import pytest

RUNNERS = sorted((Path(__file__).resolve().parents[2]
                  / "src" / "text2sql_benchmark" / "runner").glob("*.py"))


@pytest.mark.parametrize("caminho", RUNNERS, ids=lambda p: p.name)
def test_sem_nome_indefinido(caminho):
    modulo = ast.parse(caminho.read_text(encoding="utf-8"))
    definidos = set(dir(builtins))
    for no in ast.walk(modulo):
        if isinstance(no, ast.Import):
            definidos.update((a.asname or a.name.split(".")[0]) for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            definidos.update((a.asname or a.name) for a in no.names)
        elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definidos.add(no.name)
        elif isinstance(no, ast.Name) and isinstance(no.ctx, ast.Store):
            definidos.add(no.id)
        elif isinstance(no, ast.arg):
            definidos.add(no.arg)
        elif isinstance(no, ast.ExceptHandler) and no.name:
            definidos.add(no.name)
        elif isinstance(no, (ast.Global, ast.Nonlocal)):
            definidos.update(no.names)

    usados = {
        n.id for n in ast.walk(modulo)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    faltando = sorted(u for u in usados - definidos if not u.startswith("__"))
    assert not faltando, f"{caminho.name} usa nomes que nao existem: {faltando}"
