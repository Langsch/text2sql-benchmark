from text2sql_benchmark.llm.openrouter_connector import OpenRouterConnector


def _conector(**kw):
    return OpenRouterConnector("qwen/qwen3.8-27b", "k", **kw)


def test_pin_desliga_o_fallback():
    """Pinar sem desligar o fallback nao serve de nada: o roteador cairia em
    outro provedor no primeiro erro e a rodada ficaria misturada."""
    corpo = _conector(provider_pin="parasail")._provider_body()
    assert corpo["only"] == ["parasail"]
    assert corpo["allow_fallbacks"] is False


def test_quantizacao_entra_no_corpo():
    corpo = _conector(provider_pin="parasail", quantization="fp8")._provider_body()
    assert corpo["quantizations"] == ["fp8"]


def test_sem_pin_nao_manda_bloco_provider():
    assert _conector()._provider_body() == {}


class _RespostaFalsa:
    def __init__(self, provider=None, extra=None):
        if provider is not None:
            self.provider = provider
        self.model_extra = extra or {}


def test_le_o_provider_do_campo_direto():
    assert OpenRouterConnector._extrair_provider(_RespostaFalsa(provider="parasail")) == "parasail"


def test_le_o_provider_do_model_extra():
    """Campo proprio do OpenRouter, fora do schema da OpenAI: o SDK o guarda
    em model_extra em vez de expor como atributo."""
    resposta = _RespostaFalsa(extra={"provider": "deepinfra"})
    assert OpenRouterConnector._extrair_provider(resposta) == "deepinfra"


def test_provider_ausente_vira_string_vazia():
    assert OpenRouterConnector._extrair_provider(_RespostaFalsa()) == ""
