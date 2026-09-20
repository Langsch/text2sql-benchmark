from text2sql_benchmark.db.sql_split import primeiro_statement


def test_statement_unico_volta_inteiro():
    assert primeiro_statement("SELECT 1 FROM t") == "SELECT 1 FROM t"


def test_dois_statements_devolve_o_primeiro():
    """O modelo as vezes responde duas consultas; o EXPLAIN so prefixa a
    primeira e o cursor termina com o resultado da ultima, nao com um plano."""
    sql = "SELECT d.driverid FROM drivers d LIMIT 3;\nSELECT COUNT(*) FROM drivers;"
    assert primeiro_statement(sql) == "SELECT d.driverid FROM drivers d LIMIT 3"


def test_ponto_e_virgula_dentro_de_string_nao_separa():
    sql = "SELECT * FROM t WHERE nome = 'a;b'; SELECT 2"
    assert primeiro_statement(sql) == "SELECT * FROM t WHERE nome = 'a;b'"


def test_ponto_e_virgula_dentro_de_identificador_com_crase():
    sql = "SELECT `col;x` FROM t; SELECT 2"
    assert primeiro_statement(sql) == "SELECT `col;x` FROM t"


def test_ponto_e_virgula_dentro_de_aspas_duplas():
    sql = 'SELECT "col;x" FROM t; SELECT 2'
    assert primeiro_statement(sql) == 'SELECT "col;x" FROM t'


def test_ponto_e_virgula_final_sozinho():
    assert primeiro_statement("SELECT 1;") == "SELECT 1"


def test_espaco_em_branco_antes_do_primeiro_statement():
    assert primeiro_statement("\n  ; SELECT 1") == "SELECT 1"
