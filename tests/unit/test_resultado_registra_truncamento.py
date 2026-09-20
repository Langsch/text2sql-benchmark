"""O corte por teto de tokens precisa chegar ao resultado gravado.

Sem isso o corte fica invisivel: o extrator devolve o SQL parcial, que as vezes
ate executa, e o registro parece integro. A Etapa 2 ja gravava `truncated`; a
Etapa 1 nao, e e ela que produz as 500 questoes do dataset.
"""
import inspect

from text2sql_benchmark.runner import benchmark_runner
from text2sql_benchmark.storage import BenchmarkResult


def test_campo_existe_no_resultado():
    assert "truncated" in BenchmarkResult.__dataclass_fields__


def test_campo_tem_default_falso():
    campo = BenchmarkResult.__dataclass_fields__["truncated"]
    assert campo.default is False


def test_runner_propaga_o_truncamento_da_resposta():
    fonte = inspect.getsource(benchmark_runner)
    assert "truncated = llm_response.truncated" in fonte
    assert "truncated=truncated," in fonte


def test_campos_de_token_existem():
    """Sem eles nao da para recontar o consumo de saida por questao: a
    comparacao de custo entre modelos dependia de amostras avulsas e precisou
    ser retirada do relatorio."""
    for campo in ("input_tokens", "output_tokens"):
        assert campo in BenchmarkResult.__dataclass_fields__
        assert BenchmarkResult.__dataclass_fields__[campo].default == 0


def test_runner_propaga_os_tokens():
    fonte = inspect.getsource(benchmark_runner)
    assert "output_tokens = llm_response.output_tokens" in fonte
    assert "output_tokens=output_tokens," in fonte
