from text2sql_benchmark.metrics import execution_accuracy


def test_ordem_das_linhas_nao_importa():
    assert execution_accuracy([(1,), (2,)], [(2,), (1,)])


def test_linha_com_lista_nao_estoura():
    """`ARRAY_AGG` no PostgreSQL volta como lista Python, que nao entra em
    set(). Antes disso a questao virava system_error e a resposta do modelo era
    descartada mesmo estando certa."""
    pred = [(3, [1, 2, 3])]
    gold = [(3, [1, 2, 3])]
    assert execution_accuracy(pred, gold)


def test_listas_diferentes_continuam_diferentes():
    assert not execution_accuracy([(3, [1, 2])], [(3, [1, 3])])


def test_ordem_dentro_da_lista_importa():
    """Array e sequencia ordenada: [1,2] nao e o mesmo resultado que [2,1]."""
    assert not execution_accuracy([(1, [1, 2])], [(1, [2, 1])])


def test_dicionario_json_e_comparavel():
    assert execution_accuracy([({"a": 1, "b": 2},)], [({"b": 2, "a": 1},)])


def test_bytes_sao_comparaveis():
    assert execution_accuracy([(b"x",)], [(bytearray(b"x"),)])


def test_lista_aninhada():
    assert execution_accuracy([(1, [[1, 2], [3]])], [(1, [[1, 2], [3]])])


def test_resultados_diferentes():
    assert not execution_accuracy([(1,)], [(2,)])
