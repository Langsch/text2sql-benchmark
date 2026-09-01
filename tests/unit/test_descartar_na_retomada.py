from text2sql_benchmark.storage import BenchmarkResult, ResultsStore


def _r(iid, tipo):
    return BenchmarkResult(
        instance_id=iid, db_id="d", difficulty="simple", model="m", sgbd="sqlite",
        sql_generated="", sql_gold="", execution_accuracy=False, exact_match=False,
        latency_ms=0.0, explain_raw="", explain_parsed={}, error="x", error_type=tipo,
    )


def _store(tmp_path, registros):
    s = ResultsStore(tmp_path)
    s._results = list(registros)
    return s


def test_descarta_llm_error_e_system_error(tmp_path):
    """Nenhum dos dois e resultado do modelo: um e chamada que nao aconteceu,
    o outro e defeito do proprio benchmark."""
    s = _store(tmp_path, [_r(1, "llm_error"), _r(2, "system_error"), _r(3, "sql_error")])
    assert s.descartar("llm_error", "system_error") == 2
    assert [r.instance_id for r in s._results] == [3]


def test_nao_descarta_sql_error_nem_timeout(tmp_path):
    """Os dois SAO resultado — refaze-los mudaria a medicao."""
    s = _store(tmp_path, [_r(1, "sql_error"), _r(2, "timeout")])
    assert s.descartar("llm_error", "system_error") == 0
    assert len(s._results) == 2


def test_registro_sem_erro_permanece(tmp_path):
    ok = _r(1, None)
    ok.error = None
    s = _store(tmp_path, [ok])
    assert s.descartar("llm_error", "system_error") == 0


def test_sem_tipos_nao_descarta_nada(tmp_path):
    s = _store(tmp_path, [_r(1, "llm_error")])
    assert s.descartar() == 0
