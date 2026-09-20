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


def _e2(tmp_path, nome, modelo, sgbd, pares, aplicados=10, falharam=0):
    dados = [{
        "db_id": "d", "model": modelo, "dialect": sgbd, "error": None,
        "indexes_applied": aplicados, "indexes_failed": falharam,
        "query_results": [
            {"instance_id": i, "before": {"latency_ms": b}, "after": {"latency_ms": a},
             "improved": b > a, "new_index_used": True, "execution_accuracy": True}
            for i, (b, a) in enumerate(pares)
        ],
    }]
    p = tmp_path / nome
    p.write_text(json.dumps(dados), encoding="utf-8")
    return p


def _e3(tmp_path, nome, modelo, sgbd, itens):
    dados = [{
        "db_id": "d", "model": modelo, "dialect": sgbd, "error": None,
        "indexes_applied": 10, "indexes_failed": 0,
        "query_results": [
            {"instance_id": i, "before": {"latency_ms": b}, "after": {"latency_ms": a},
             "improved": b > a, "new_index_used": usou, "execution_accuracy": ok}
            for i, (b, a, ok, usou) in enumerate(itens)
        ],
    }]
    p = tmp_path / nome
    p.write_text(json.dumps(dados), encoding="utf-8")
    return p


def test_speedup_usa_mediana_e_nao_media(tmp_path):
    """A distribuicao tem cauda longa — uma query saiu de 408 s para 2,1 ms —
    e a media seria dominada por outliers."""
    a = _arquivo(tmp_path, "a.json", "A", "sqlite", [True])
    e2 = _e2(tmp_path, "e2.json", "A", "sqlite", [(10, 10), (20, 10), (1000, 1)])
    rep = ComparativeReport.from_files([a], [e2])
    assert rep._indices[0].med_gabarito == pytest.approx(2.0)


def test_etapa3_separa_corretas_de_incorretas(tmp_path):
    a = _arquivo(tmp_path, "a.json", "A", "sqlite", [True])
    e2 = _e2(tmp_path, "e2.json", "A", "sqlite", [(10, 5)])
    e3 = _e3(tmp_path, "e3.json", "A", "sqlite",
             [(10, 5, True, True), (40, 5, False, False)])
    c = ComparativeReport.from_files([a], [e2], [e3])._indices[0]
    assert c.med_corretas == pytest.approx(2.0)
    assert c.med_incorretas == pytest.approx(8.0)
    assert c.pct_indice_novo == pytest.approx(50.0)
    assert c.medidas == 2


def test_registro_com_erro_e_ignorado(tmp_path):
    """Um banco que falhou na Etapa 2 nao pode entrar na conta de indices."""
    a = _arquivo(tmp_path, "a.json", "A", "sqlite", [True])
    dados = json.loads(_e2(tmp_path, "e2.json", "A", "sqlite", [(10, 5)]).read_text())
    dados.append({"db_id": "x", "model": "A", "dialect": "sqlite", "error": "falhou",
                  "indexes_applied": 99, "indexes_failed": 99, "query_results": []})
    p = tmp_path / "e2b.json"
    p.write_text(json.dumps(dados), encoding="utf-8")
    c = ComparativeReport.from_files([a], [p])._indices[0]
    assert c.aplicados == 10 and c.falharam == 0


def test_sem_stage3_so_traz_a_etapa2(tmp_path):
    a = _arquivo(tmp_path, "a.json", "A", "sqlite", [True])
    e2 = _e2(tmp_path, "e2.json", "A", "sqlite", [(10, 5)])
    c = ComparativeReport.from_files([a], [e2])._indices[0]
    assert c.med_gabarito == pytest.approx(2.0)
    assert c.med_gerado == 0.0 and c.medidas == 0


def test_percentual_de_falha_de_indice(tmp_path):
    a = _arquivo(tmp_path, "a.json", "A", "sqlite", [True])
    e2 = _e2(tmp_path, "e2.json", "A", "sqlite", [(10, 5)], aplicados=81, falharam=19)
    assert ComparativeReport.from_files([a], [e2])._indices[0].pct_falha_indice == pytest.approx(19.0)


def test_csv_de_indices_sai_quando_ha_etapa2(tmp_path):
    a = _arquivo(tmp_path, "a.json", "A", "sqlite", [True])
    e2 = _e2(tmp_path, "e2.json", "A", "sqlite", [(10, 5)])
    nomes = {g.name for g in ComparativeReport.from_files([a], [e2]).exportar_csv(tmp_path / "o")}
    assert "indices_por_modelo.csv" in nomes
