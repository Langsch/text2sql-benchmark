from __future__ import annotations

from ..config import BenchmarkConfig, LLMConfig
from .anthropic_connector import AnthropicConnector
from .base import LLMConnector
from .google_connector import GoogleConnector
from .groq_connector import GroqConnector
from .openai_connector import OpenAIConnector
from .openrouter_connector import OpenRouterConnector


class PinagemAusente(RuntimeError):
    """Modelo servido por varios provedores sem provedor fixado."""


def build_connector(cfg: LLMConfig, exigir_pin: bool = True) -> LLMConnector:
    """Constroi o conector de um modelo.

    O despacho olha `cfg.provider`, nunca o nome do modelo: a slug
    "openai/gpt-5.6-luna" e do OpenRouter, e casar por substring "gpt" a
    mandaria para a API nativa da OpenAI com um nome de modelo invalido.
    """
    if cfg.provider == "openrouter":
        if exigir_pin and cfg.exige_pin and not cfg.provider_pin:
            from ..config import PROVEDORES_POR_MODELO

            n = PROVEDORES_POR_MODELO.get(cfg.model_name, "varios")
            raise PinagemAusente(
                f"{cfg.model_name} e servido por {n} provedores no OpenRouter e "
                f"nao tem provedor fixado. Sem pinagem o roteamento troca de "
                f"provedor no meio da rodada e o resultado nao e reproduzivel.\n"
                f"  1. Descubra quem atende:  python cli.py smoke --model {cfg.model_name}\n"
                f"  2. Fixe no .env:          OPENROUTER_PIN_"
                f"{cfg.model_name.upper().replace('/', '_').replace('-', '_').replace('.', '_')}"
                f"=<provedor>"
            )
        return OpenRouterConnector(
            cfg.model_name,
            cfg.api_key,
            cfg.provider_pin,
            cfg.quantization,
            cfg.reasoning_effort,
        )
    if cfg.provider == "anthropic":
        return AnthropicConnector(cfg.model_name, cfg.api_key)
    if cfg.provider == "openai":
        return OpenAIConnector(cfg.model_name, cfg.api_key)
    if cfg.provider == "google":
        return GoogleConnector(cfg.model_name, cfg.api_key)
    if cfg.provider == "groq":
        return GroqConnector(cfg.model_name, cfg.api_key)
    raise ValueError(f"Provedor sem suporte: {cfg.provider!r} ({cfg.model_name})")


def build_llm_connectors(
    cfg: BenchmarkConfig, model: str | None = None, exigir_pin: bool = True
) -> list[LLMConnector]:
    """Conectores de todos os modelos com chave configurada.

    Com `model`, filtra por nome exato e deixa o erro de pinagem subir — quem
    pediu aquele modelo precisa saber por que ele nao vai rodar. Sem `model`,
    modelos sem pinagem sao omitidos silenciosamente, como ja acontece com os
    que nao tem chave.
    """
    conectores: list[LLMConnector] = []
    for llm_cfg in cfg.llms:
        if not llm_cfg.api_key:
            continue
        if model and llm_cfg.model_name != model:
            continue
        if model:
            conectores.append(build_connector(llm_cfg, exigir_pin))
            continue
        try:
            conectores.append(build_connector(llm_cfg, exigir_pin))
        except PinagemAusente:
            continue
    return conectores
