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
