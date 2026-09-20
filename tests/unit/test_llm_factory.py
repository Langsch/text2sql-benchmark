import pytest

from text2sql_benchmark.config import BenchmarkConfig, LLMConfig
from text2sql_benchmark.llm.anthropic_connector import AnthropicConnector
from text2sql_benchmark.llm.factory import (
    PinagemAusente,
    build_connector,
    build_llm_connectors,
)
from text2sql_benchmark.llm.openrouter_connector import OpenRouterConnector


def _cfg(*llms):
    return BenchmarkConfig(
        bird_data_path="/tmp",
        use_evidence=True,
        timeout_seconds=30,
        output_dir="/tmp",
        llms=list(llms),
    )


def test_despacha_pelo_provider_e_nao_pelo_nome():
    """A slug 'openai/gpt-5.6-luna' e do OpenRouter, nao da OpenAI.

    O despacho antigo casava por substring: "gpt" no nome mandava para a API
    nativa da OpenAI, que rejeitaria a slug com barra.
    """
    conector = build_connector(
        LLMConfig("openai/gpt-5.6-luna", "k", provider="openrouter", provider_pin="openai")
    )
    assert isinstance(conector, OpenRouterConnector)


def test_sonnet_nativo_continua_na_anthropic():
    conector = build_connector(LLMConfig("claude-sonnet-5", "k", provider="anthropic"))
    assert isinstance(conector, AnthropicConnector)


def test_modelo_multiprovedor_sem_pin_e_recusado():
    with pytest.raises(PinagemAusente) as exc:
        build_connector(LLMConfig("deepseek/deepseek-v4-flash-0731", "k"))
    # a mensagem precisa dizer o que fazer, nao so que deu errado
    assert "smoke" in str(exc.value)
    assert "OPENROUTER_PIN_DEEPSEEK_DEEPSEEK_V4_FLASH_0731" in str(exc.value)


def test_pin_libera_o_modelo_multiprovedor():
    conector = build_connector(
        LLMConfig("qwen/qwen3.8-27b", "k", provider_pin="parasail", quantization="fp8")
    )
    assert conector.provider_pin == "parasail"
    assert conector.quantization == "fp8"


def test_smoke_pode_dispensar_a_pinagem():
    """Sem isso nao haveria como descobrir qual provedor pinar."""
    conector = build_connector(
        LLMConfig("qwen/qwen3.8-27b", "k"), exigir_pin=False
    )
    assert isinstance(conector, OpenRouterConnector)


def test_modelo_sem_chave_e_omitido():
    cfg = _cfg(
        LLMConfig("qwen/qwen3.8-27b", "", provider_pin="parasail"),
        LLMConfig("claude-sonnet-5", "k", provider="anthropic"),
    )
    nomes = [c.model_name for c in build_llm_connectors(cfg)]
    assert nomes == ["claude-sonnet-5"]


def test_sem_pin_e_omitido_da_lista_mas_explode_se_for_pedido():
    """Na lista geral, pular; quando o modelo foi pedido por nome, avisar.

    Omitir silenciosamente um modelo pedido explicitamente faria a rodada
    terminar sem dados e sem explicacao.
    """
    cfg = _cfg(LLMConfig("qwen/qwen3.8-27b", "k"))
    assert build_llm_connectors(cfg) == []
    with pytest.raises(PinagemAusente):
        build_llm_connectors(cfg, model="qwen/qwen3.8-27b")
