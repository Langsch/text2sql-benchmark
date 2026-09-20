from text2sql_benchmark.metrics import exact_match


def test_identicas():
    assert exact_match("SELECT a FROM t", "SELECT a FROM t")


def test_caixa_e_espacos_nao_importam():
    assert exact_match("select   a\nfrom t", "SELECT a FROM t")


def test_ponto_e_virgula_final_nao_importa():
    """Diferenca puramente tipografica. Sem isso o Luna tinha Exact Match zero
    em 500 questoes, porque encerrava toda consulta com `;` e o gabarito do
    BIRD nao usa terminador."""
    assert exact_match("SELECT a FROM t;", "SELECT a FROM t")
    assert exact_match("SELECT a FROM t ;  ", "SELECT a FROM t")


def test_ponto_e_virgula_no_meio_continua_diferenca():
    """Um `;` interno separa comandos — o modelo devolveu duas consultas."""
    assert not exact_match("SELECT a FROM t; SELECT b FROM u", "SELECT a FROM t")


def test_aspas_sao_normalizadas():
    assert exact_match('SELECT "a" FROM t', "SELECT `a` FROM t")


def test_consultas_diferentes():
    assert not exact_match("SELECT a FROM t", "SELECT b FROM t")


def test_alias_diferente_nao_e_match():
    """Alias e escolha de escrita: distinguir isso e o proposito da metrica."""
    assert not exact_match("SELECT T1.a FROM t AS T1", "SELECT T2.a FROM t AS T2")
