"""Testes da extracao de SQL da resposta bruta do LLM.

Regressao: os conectores Anthropic, OpenAI e Google nao removiam as cercas
markdown, entao o texto ia cru para o banco e a questao era contabilizada
como erro de execucao — inflando a taxa de falha do modelo por um motivo
que nao era do modelo.
"""

from src.text2sql_benchmark.llm.sql_extract import extract_sql


def test_remove_cerca_com_linguagem():
    assert extract_sql("```sql\nSELECT 1;\n```") == "SELECT 1;"


def test_remove_cerca_sem_linguagem():
    assert extract_sql("```\nSELECT 2;\n```") == "SELECT 2;"


def test_texto_puro_passa_intacto():
    assert extract_sql("SELECT 3;") == "SELECT 3;"


def test_remove_bloco_de_raciocinio():
    bruto = "<think>penso um pouco</think>\n```sql\nSELECT 4;\n```"
    assert extract_sql(bruto) == "SELECT 4;"


def test_cerca_aberta_sem_fechamento():
    """Acontece quando a resposta e truncada em max_tokens."""
    assert extract_sql("```sql\nSELECT 5;") == "SELECT 5;"


def test_varias_cercas_sao_concatenadas():
    bruto = "```sql\nSELECT 6;\n```\ncomentario\n```sql\nSELECT 7;\n```"
    assert extract_sql(bruto) == "SELECT 6;\nSELECT 7;"


def test_espacos_sao_removidos():
    assert extract_sql("  SELECT 8;  ") == "SELECT 8;"


def test_vazio():
    assert extract_sql("") == ""
