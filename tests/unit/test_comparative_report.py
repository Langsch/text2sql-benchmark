import json

import pytest

from text2sql_benchmark.report.comparative_report import ComparativeReport


def _arquivo(tmp_path, nome, modelo, sgbd, acertos, tipos_erro=None):
    tipos_erro = tipos_erro or {}
    dados = [
        {
            "instance_id": i,
            "model": modelo,
            "sgbd": sgbd,
            "execution_accuracy": ok,
            "error": "x" if i in tipos_erro else None,
            "error_type": tipos_erro.get(i),
        }
        for i, ok in enumerate(acertos)
    ]
    p = tmp_path / nome
    p.write_text(json.dumps(dados), encoding="utf-8")
    return p


def test_acuracia_ignora_medicao_invalida(tmp_path):
    """llm_error e system_error nao sao resultado do modelo: contá-los como
    erro atribuiria ao modelo um problema de API ou do proprio benchmark."""
    p = _arquivo(tmp_path, "a.json", "A", "sqlite",
                 [True, True, False, False], {3: "llm_error"})
    rep = ComparativeReport.from_files([p])
    celula = rep._celulas[0]
    assert len(celula.acertos) == 3          # a invalida saiu
    assert celula.invalidas == {3}
    assert celula.ex == pytest.approx(200 / 3)


def test_sql_error_e_timeout_continuam_contando_como_erro(tmp_path):
    """SQL invalido e query lenta SAO resultado — do modelo e de eficiencia."""
    p = _arquivo(tmp_path, "a.json", "A", "sqlite",
                 [True, False, False], {1: "sql_error", 2: "timeout"})
    celula = ComparativeReport.from_files([p])._celulas[0]
    assert len(celula.acertos) == 3
    assert celula.ex == pytest.approx(100 / 3)


def test_pareamento_usa_so_questoes_medidas_nos_dois(tmp_path):
    a = _arquivo(tmp_path, "a.json", "A", "sqlite", [True, True, True], {0: "llm_error"})
    b = _arquivo(tmp_path, "b.json", "B", "sqlite", [True, False, True])
    rep = ComparativeReport.from_files([a, b])
    xa, xb, descartadas = rep._pares(rep._celulas[0], rep._celulas[1])
    assert len(xa) == len(xb) == 2
    assert descartadas == 1


def test_modelos_preservam_ordem_de_entrada(tmp_path):
    a = _arquivo(tmp_path, "a.json", "zeta", "sqlite", [True])
    b = _arquivo(tmp_path, "b.json", "alfa", "sqlite", [True])
    assert ComparativeReport.from_files([a, b]).modelos == ["zeta", "alfa"]


def test_agrupa_por_sgbd(tmp_path):
    a = _arquivo(tmp_path, "a.json", "A", "sqlite", [True])
    b = _arquivo(tmp_path, "b.json", "A", "postgresql", [False])
    rep = ComparativeReport.from_files([a, b])
    assert set(rep._por_sgbd) == {"sqlite", "postgresql"}


def test_arquivo_vazio_e_recusado(tmp_path):
    p = tmp_path / "vazio.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="sem registros"):
        ComparativeReport.from_files([p])


def test_csv_sai_com_as_duas_tabelas(tmp_path):
    a = _arquivo(tmp_path, "a.json", "A", "sqlite", [True, True, False])
    b = _arquivo(tmp_path, "b.json", "B", "sqlite", [True, False, False])
    gerados = ComparativeReport.from_files([a, b]).exportar_csv(tmp_path / "out")
    nomes = {g.name for g in gerados}
    assert nomes == {"acuracia_por_modelo.csv", "divergencias.csv"}
    assert all(g.read_text(encoding="utf-8").strip() for g in gerados)
