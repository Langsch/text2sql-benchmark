"""Testes das funções de análise usadas na conferência do artigo."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("reproduzir", RAIZ / "analise" / "reproduzir.py")
rep = importlib.util.module_from_spec(_spec)
sys.modules["reproduzir"] = rep  # @dataclass precisa achar o módulo registrado
_spec.loader.exec_module(rep)


def test_colunas_indexadas_remove_ordem_e_prefixo() -> None:
    # Regressão: o cálculo anterior não removia DESC e deixava de reconhecer
    # que o índice cobre a coluna.
    stmts = [
        "CREATE INDEX i1 ON posts(CreationDate DESC);",
        "CREATE INDEX i2 ON schools(County(255), `Virtual`);",
        'CREATE INDEX i3 ON "races" ("year" ASC, round)',
    ]
    assert rep.colunas_indexadas(stmts) == {
        "creationdate", "county", "virtual", "year", "round",
    }


def test_colunas_de_predicado_inclui_juncao_e_funcoes() -> None:
    sql = ("SELECT T1.name FROM a AS T1 JOIN b AS T2 ON T1.id = T2.a_id "
           "WHERE strftime('%Y', T2.dt) = '2012' ORDER BY T1.score")
    assert rep.colunas_de_predicado(sql, "sqlite") == {"id", "a_id", "dt", "score"}


def test_mcnemar_reproduz_o_par_mais_proximo() -> None:
    # 180 contra 174 discordâncias: p = 0,79 citado no artigo.
    _, p = rep._chi2_cc(180, 174)
    assert round(p, 2) == 0.79


def test_mcnemar_exato_simetrico_e_limitado() -> None:
    assert rep._exato(10, 10) == 1.0
    assert rep._exato(3, 12) == pytest.approx(rep._exato(12, 3))
    assert rep._exato(0, 0) == 1.0


def test_potencia_formata_como_o_artigo() -> None:
    assert rep._potencia(1.8e-05) == "2 × 10⁻⁵"


@pytest.mark.skipif(not (RAIZ / "results" / "runs").exists(),
                    reason="arquivos de resultado ausentes (ver README, Disponibilidade dos dados)")
def test_manifesto_integro() -> None:
    import json

    man = json.loads((RAIZ / "analise" / "manifesto.json").read_text(encoding="utf-8"))
    assert len(man["celulas"]) == 15
    for c in man["celulas"]:
        for etapa in ("etapa1", "etapa2", "etapa3"):
            ref = c[etapa]
            assert rep.sha256(RAIZ / ref["arquivo"]) == ref["sha256"], ref["arquivo"]
